"""Central configuration for the pARallax local server.

Every value is overridable via environment variables (see `.env.example`).
Nothing secret is ever hardcoded in source.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Load `server/.env` if present. Never committed - see .gitignore.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover - dotenv is optional at runtime
    pass


def _env(name: str, default=None):
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, default))
    except (TypeError, ValueError):
        return default


# --- Segmentation service -------------------------------------------------
# URL of the HTTP background-removal / salient-object-detection service.
# The upstream project relied on a community CoreWeave endpoint that is no
# longer guaranteed to be alive; point this at your own deployment.
SEGMENTATION_SERVICE_URL = _env("SEGMENTATION_SERVICE_URL", "http://localhost:8081")
SEGMENTATION_TIMEOUT = _env_int("SEGMENTATION_TIMEOUT", 30)

# --- Local server ---------------------------------------------------------
SERVER_HOST = _env("SERVER_HOST", "0.0.0.0")
SERVER_PORT = _env_int("SERVER_PORT", 8080)
DEBUG = _env("DEBUG", "false").lower() in ("1", "true", "yes")

# Comma-separated list of allowed CORS origins. "*" is convenient on a trusted
# LAN during development but should be narrowed for any real deployment.
CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", "*").split(",") if o.strip()]

# Write the intermediate images to disk for debugging. Off by default so a
# normal run leaves no stray files in the repo.
SAVE_DEBUG_IMAGES = _env("SAVE_DEBUG_IMAGES", "false").lower() in ("1", "true", "yes")

# Directory for runtime artifacts (gitignored).
TMP_DIR = Path(_env("TMP_DIR", Path(__file__).resolve().parent.parent / "tmp"))

# --- Image pipeline -------------------------------------------------------
MAX_VIEW_SIZE = _env_int("MAX_VIEW_SIZE", 700)
MAX_SCREENSHOT_SIZE = _env_int("MAX_SCREENSHOT_SIZE", 400)

# --- Paste target ---------------------------------------------------------
# Which editor to paste cutouts into. See server/src/targets/.
#
#   gimp       free, cross-platform, via the Script-Fu server (default)
#   photoshop  macOS only, via AppleScript
PASTE_TARGET = _env("PASTE_TARGET", "gimp")

# --- Paste sizing ----------------------------------------------------------
# A cutout arrives at whatever resolution the camera produced - a 12 MP phone
# photo yields a ~3000x4000 layer, which on a 1920x1080 canvas hangs off every
# edge and is useless. Scale so the layer occupies at most this fraction of the
# canvas in both dimensions.
PASTE_MAX_FRACTION = _env_float("PASTE_MAX_FRACTION", 0.4)

# Whether a cutout smaller than the target may be scaled up. Off by default:
# enlarging a small crop just magnifies its softness.
PASTE_ALLOW_UPSCALE = _env("PASTE_ALLOW_UPSCALE", "false").lower() in ("1", "true", "yes")

# --- GIMP ------------------------------------------------------------------
# Script-Fu server address. Enable it in GIMP: Filters > Script-Fu > Start
# Server. It has NO authentication, so keep it bound to localhost.
GIMP_HOST = _env("GIMP_HOST", "127.0.0.1")
GIMP_PORT = _env_int("GIMP_PORT", 10008)
GIMP_TIMEOUT = _env_int("GIMP_TIMEOUT", 30)

# --- Photoshop integration ------------------------------------------------
# Leave blank to auto-detect the running Photoshop application by name.
PHOTOSHOP_APP_NAME = _env("PHOTOSHOP_APP_NAME", "")
PHOTOSHOP_DOC_WIDTH = _env_int("PHOTOSHOP_DOC_WIDTH", 2121)
PHOTOSHOP_DOC_HEIGHT = _env_int("PHOTOSHOP_DOC_HEIGHT", 1280)
SCREEN_PIXEL_DENSITY = _env_int("SCREEN_PIXEL_DENSITY", 2)
