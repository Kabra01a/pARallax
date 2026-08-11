"""pARallax - segmentation service.

Standalone HTTP service that takes an image and returns a saliency mask.
Runs BiRefNet (MIT) via rembg. Replaces the dead public U^2-Net endpoint the
upstream project depended on.

Contract expected by the local server (`server/src/main.py`):

    POST /            multipart field `data` (image)  ->  image/png, grayscale mask

Also provided for debugging and demos:

    GET  /            health + active model
    GET  /ping        liveness
    POST /cutout      multipart field `data`  ->  image/png, RGBA cutout

The model is loaded lazily on first inference so the process starts instantly
and the health endpoint answers before weights are downloaded.
"""

import io
import logging
import os
import time

from flask import Flask, jsonify, make_response, request, send_file

import config

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_session = None
_providers: list[str] = []


def get_session():
    """Load the rembg session once, on first use.

    First call downloads the model weights to ~/.u2net (a few hundred MB for
    the full BiRefNet), so expect a long first request.
    """
    global _session, _providers
    if _session is None:
        import session as session_factory

        logger.info("loading model %r", config.MODEL_NAME)
        logger.info("first run downloads weights; with CoreML it also compiles "
                    "the graph, which takes minutes but is cached afterwards")
        start = time.time()
        _session, _providers = session_factory.create_session(config.MODEL_NAME)
        logger.info("model ready in %.1fs", time.time() - start)
    return _session


def _read_upload():
    """Return the uploaded image bytes, or raise ValueError.

    Accepts `data` (what the local server sends) plus `file` and `image` as
    aliases, so the service is easy to exercise with curl.
    """
    for field in ("data", "file", "image"):
        if field in request.files:
            payload = request.files[field].read()
            if not payload:
                raise ValueError(f"file param `{field}` was empty")
            return payload

    if request.data:
        return request.data

    raise ValueError("missing file param `data`")


def _infer(payload: bytes, only_mask: bool) -> tuple[bytes, float]:
    from rembg import remove

    start = time.time()
    result = remove(
        payload,
        session=get_session(),
        only_mask=only_mask,
        post_process_mask=config.POST_PROCESS_MASK,
        alpha_matting=config.ALPHA_MATTING,
        alpha_matting_foreground_threshold=config.ALPHA_MATTING_FG_THRESHOLD,
        alpha_matting_background_threshold=config.ALPHA_MATTING_BG_THRESHOLD,
        alpha_matting_erode_size=config.ALPHA_MATTING_ERODE_SIZE,
    )
    return result, (time.time() - start) * 1000


@app.route("/", methods=["GET"])
@app.route("/ping", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "pARallax segmentation",
        "model": config.MODEL_NAME,
        "tier": config.model_tier(),
        "model_loaded": _session is not None,
        "providers": _providers or "not loaded yet",
        "post_process_mask": config.POST_PROCESS_MASK,
        "alpha_matting": config.ALPHA_MATTING,
    })


@app.route("/", methods=["OPTIONS"])
@app.route("/cutout", methods=["OPTIONS"])
def options():
    return make_response("", 204)


@app.route("/", methods=["POST"])
def mask():
    """Return a grayscale saliency mask. This is what the local server calls."""
    try:
        payload = _read_upload()
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400

    try:
        result, elapsed = _infer(payload, only_mask=True)
    except Exception as exc:
        logger.exception("inference failed")
        return jsonify({"status": "error", "error": str(exc)}), 500

    logger.info("mask produced in %.0f ms (%d bytes in)", elapsed, len(payload))
    response = send_file(io.BytesIO(result), mimetype="image/png")
    response.headers["X-Inference-Ms"] = f"{elapsed:.0f}"
    response.headers["X-Model"] = config.MODEL_NAME
    return response


@app.route("/cutout", methods=["POST"])
def cutout():
    """Return an RGBA cutout. Handy for eyeballing quality directly."""
    try:
        payload = _read_upload()
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400

    try:
        result, elapsed = _infer(payload, only_mask=False)
    except Exception as exc:
        logger.exception("inference failed")
        return jsonify({"status": "error", "error": str(exc)}), 500

    logger.info("cutout produced in %.0f ms", elapsed)
    response = send_file(io.BytesIO(result), mimetype="image/png")
    response.headers["X-Inference-Ms"] = f"{elapsed:.0f}"
    return response


def main():
    import argparse

    parser = argparse.ArgumentParser(description="pARallax segmentation service")
    parser.add_argument("--model", default=config.MODEL_NAME,
                        help="rembg model name, e.g. birefnet-general")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--preload", action="store_true",
                        help="load the model at startup instead of on first request")
    args = parser.parse_args()

    config.MODEL_NAME = args.model
    config.warn_if_restricted_model()

    if args.preload:
        get_session()

    logger.info("model: %s", config.MODEL_NAME)
    logger.info("listening on http://%s:%s", args.host, args.port)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
