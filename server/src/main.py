"""pARallax - local server.

Bridges the mobile app and the desktop image editor:

  POST /cut    image -> segmentation service -> transparent PNG (returned + cached)
  POST /paste  image -> locate on screen (SIFT homography) -> paste into Photoshop
"""

import argparse
import io
import logging
import time
from datetime import datetime

import numpy as np
import pyscreenshot
import requests
from flask import Flask, jsonify, make_response, request, send_file
from flask_cors import CORS
from PIL import Image

import config
import screenpoint
import targets

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
logger = logging.getLogger(__name__)

# The most recent cut result, reused by /paste.
CUT_CACHE_PATH = config.TMP_DIR / "cut_current.png"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": config.CORS_ORIGINS}})


def _error(message: str, status: int = 400):
    return jsonify({"status": "error", "error": message}), status


def _read_upload():
    """Extract the uploaded image bytes, or raise ValueError."""
    if "data" not in request.files:
        raise ValueError("missing file param `data`")
    payload = request.files["data"].read()
    if not payload:
        raise ValueError("empty image")
    return payload


def _save_debug(name: str, payload: bytes | None, image=None):
    """Write an intermediate image for inspection, when SAVE_DEBUG_IMAGES is on.

    Accepts either raw bytes or a PIL image. The screenshot is worth keeping:
    if it shows only wallpaper, the terminal is missing macOS Screen Recording
    permission, which otherwise presents as a mysterious matching failure.
    """
    if not config.SAVE_DEBUG_IMAGES:
        return
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = config.TMP_DIR / name
    if image is not None:
        image.save(path)
    else:
        path.write_bytes(payload)
    logger.debug("wrote debug image %s", name)


@app.after_request
def add_cors_headers(response):
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type,Authorization,Accept")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response


@app.route("/", methods=["OPTIONS"])
@app.route("/ping", methods=["OPTIONS"])
@app.route("/cut", methods=["OPTIONS"])
@app.route("/paste", methods=["OPTIONS"])
def handle_options():
    return make_response("", 204)


@app.route("/", methods=["GET"])
@app.route("/ping", methods=["GET"])
def ping():
    payload = {
        "status": "ok",
        "message": "pARallax server",
        "segmentation_service": config.SEGMENTATION_SERVICE_URL,
        "paste_target": config.PASTE_TARGET,
    }
    try:
        target = targets.get_target(config.PASTE_TARGET)
        ready, detail = target.is_available()
        payload["target_ready"] = ready
        payload["target_detail"] = detail
    except Exception as exc:
        payload["target_ready"] = False
        payload["target_detail"] = str(exc)
    return jsonify(payload)


@app.route("/cut", methods=["POST"])
def cut():
    start = time.time()
    logger.info("CUT")

    try:
        data = _read_upload()
    except ValueError as exc:
        return _error(str(exc))

    _save_debug("cut_received.jpg", data)

    # --- segmentation --------------------------------------------------
    try:
        response = requests.post(
            config.SEGMENTATION_SERVICE_URL,
            files={"data": ("image.jpg", data)},
            timeout=config.SEGMENTATION_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.error("segmentation service unreachable: %s", exc)
        return _error(f"segmentation service unreachable: {exc}", 502)

    if response.status_code != 200:
        logger.error("segmentation failed (%s): %s", response.status_code, response.text[:200])
        return _error("segmentation service returned an error", 502)

    # --- compositing ---------------------------------------------------
    try:
        mask = Image.open(io.BytesIO(response.content)).convert("L")
        image = Image.open(io.BytesIO(data)).convert("RGBA")
    except OSError as exc:
        return _error(f"could not decode image: {exc}", 502)

    if mask.size != image.size:
        logger.debug("resizing mask %s -> %s", mask.size, image.size)
        mask = mask.resize(image.size, Image.Resampling.LANCZOS)

    output = Image.new("RGBA", image.size, (0, 0, 0, 0))
    output.paste(image, (0, 0), mask)

    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    output.save(CUT_CACHE_PATH, "PNG")

    buffer = io.BytesIO()
    output.save(buffer, format="PNG")
    buffer.seek(0)

    logger.info("cut completed in %.2fs", time.time() - start)
    return send_file(buffer, mimetype="image/png", as_attachment=True, download_name="cut.png")


@app.route("/paste", methods=["POST"])
def paste():
    start = time.time()
    logger.info("PASTE")

    try:
        data = _read_upload()
    except ValueError as exc:
        return _error(str(exc))

    _save_debug("paste_received.jpg", data)

    if not CUT_CACHE_PATH.exists():
        return _error("nothing to paste - perform a cut first", 409)

    try:
        view = Image.open(io.BytesIO(data))
    except OSError as exc:
        return _error(f"could not decode image: {exc}")

    view.thumbnail((config.MAX_VIEW_SIZE, config.MAX_VIEW_SIZE))

    logger.debug("grabbing screenshot")
    try:
        screen = pyscreenshot.grab()
    except Exception as exc:
        # On macOS 10.15+ a screenshot without Screen Recording permission
        # either fails outright or silently returns the desktop wallpaper with
        # every window stripped out - which looks like a matching failure
        # rather than a permissions problem. Say so explicitly.
        logger.error("screen capture failed: %s", exc)
        return _error(
            "could not capture the screen. On macOS, grant Screen Recording "
            "permission to your terminal in System Settings > Privacy & "
            "Security > Screen & System Audio Recording, then fully quit and "
            "reopen the terminal.", 500)

    screen_width, screen_height = screen.size
    screen.thumbnail((config.MAX_SCREENSHOT_SIZE, config.MAX_SCREENSHOT_SIZE))
    _save_debug("paste_screenshot.png", None, image=screen)

    logger.debug("locating view within screen")
    x, y = screenpoint.project(
        np.array(view.convert("L")),
        np.array(screen.convert("L")),
    )

    if x == -1 and y == -1:
        logger.info("screen not found (%.2fs)", time.time() - start)
        if config.SAVE_DEBUG_IMAGES:
            logger.info("inspect %s — if it shows only your wallpaper with no "
                        "windows, the terminal lacks macOS Screen Recording "
                        "permission", config.TMP_DIR / "paste_screenshot.png")
        return jsonify({
            "status": "screen not found",
            "hint": "the screen must look like the photo when the request "
                    "arrives; on macOS also check Screen Recording permission",
        })

    # Scale the match back up from the downsampled screenshot.
    x = int(x / screen.size[0] * screen_width)
    y = int(y / screen.size[1] * screen_height)
    logger.info("screen coordinates: (%s, %s)", x, y)

    layer_name = datetime.now().strftime("parallax-%Y%m%d-%H%M%S")
    try:
        target = targets.get_target(config.PASTE_TARGET)
    except ValueError as exc:
        return _error(str(exc), 500)

    err = target.paste(str(CUT_CACHE_PATH), layer_name, x, y,
                       screen_size=(screen_width, screen_height))
    if err is not None:
        logger.error("%s paste failed: %s", target.display_name, err)
        return _error(err, 502)

    logger.info("paste completed in %.2fs", time.time() - start)
    return jsonify({
        "status": "ok",
        "x": x,
        "y": y,
        "target": target.name,
        "layer": layer_name,
    })


def main():
    parser = argparse.ArgumentParser(description="pARallax local server")
    parser.add_argument("--segmentation_service_url", default=config.SEGMENTATION_SERVICE_URL,
                        help="URL of the background-removal HTTP service")
    parser.add_argument("--port", type=int, default=config.SERVER_PORT)
    parser.add_argument("--host", default=config.SERVER_HOST)
    parser.add_argument("--debug", action="store_true", default=config.DEBUG)
    parser.add_argument("--target", default=config.PASTE_TARGET,
                        choices=targets.available_names(),
                        help="which editor to paste into")
    args = parser.parse_args()

    # CLI flags win over environment configuration.
    config.SEGMENTATION_SERVICE_URL = args.segmentation_service_url
    config.PASTE_TARGET = args.target

    logger.info("segmentation service: %s", config.SEGMENTATION_SERVICE_URL)

    target = targets.get_target(config.PASTE_TARGET)
    ready, detail = target.is_available()
    logger.info("paste target: %s — %s", target.display_name, detail)
    if not ready:
        logger.warning("target is not ready; /paste will fail until it is")
    logger.info("listening on http://%s:%s", args.host, args.port)

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
