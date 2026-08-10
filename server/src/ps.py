"""Adobe Photoshop integration (macOS).

Drives Photoshop via AppleScript's `do javascript`, which executes an
ExtendScript payload inside the running application. This route does NOT need
the Photoshop "Remote Connection" password - that is only required for the
socket-based protocol used by the upstream project.

NOTE: this module is macOS-only. A cross-platform UXP plugin is the planned
replacement; see README "Roadmap".
"""

import json
import logging
import os
import subprocess
from functools import lru_cache

import config

logger = logging.getLogger(__name__)


def _run_osascript(script: str, timeout: int = 30):
    """Run an AppleScript snippet, returning (stdout, error_or_None)."""
    try:
        process = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return None, "osascript not found - Photoshop integration requires macOS"
    except subprocess.TimeoutExpired:
        return None, f"AppleScript timed out after {timeout}s"

    if process.returncode != 0:
        return None, (process.stderr.decode().strip() or "unknown AppleScript error")

    return process.stdout.decode().strip(), None


@lru_cache(maxsize=1)
def detect_photoshop_name():
    """Return the name of the running Photoshop process, or None.

    Avoids hardcoding a specific release ("Adobe Photoshop 2025"), which breaks
    every time the user upgrades.
    """
    if config.PHOTOSHOP_APP_NAME:
        return config.PHOTOSHOP_APP_NAME

    script = (
        'tell application "System Events" to get name of every application '
        'process whose name contains "Photoshop"'
    )
    stdout, err = _run_osascript(script, timeout=10)
    if err or not stdout:
        logger.warning("Could not detect Photoshop: %s", err or "not running")
        return None

    # osascript returns a comma-separated AppleScript list.
    names = [n.strip() for n in stdout.split(",") if n.strip()]
    if not names:
        return None

    logger.info("Detected Photoshop application: %s", names[0])
    return names[0]


def get_screen_size():
    """Return (width, height) of the desktop, or None if unavailable."""
    script = 'tell application "Finder" to get bounds of window of desktop'
    stdout, err = _run_osascript(script, timeout=10)
    if err or not stdout:
        logger.warning("Could not read screen bounds: %s", err)
        return None

    try:
        left, top, right, bottom = (int(v) for v in stdout.split(", "))
    except ValueError:
        logger.warning("Unexpected screen bounds format: %r", stdout)
        return None

    return right - left, bottom - top


def _build_jsx(image_path: str, layer_name: str, dx: float, dy: float) -> str:
    """Build the ExtendScript payload.

    Paths and names are injected as JSON literals so quotes, backslashes and
    unicode in filenames cannot break out of the script (the previous
    implementation used naive string escaping).
    """
    return f"""
    (function () {{
        try {{
            var doc = app.activeDocument;
            var originalUnits = app.preferences.rulerUnits;
            app.preferences.rulerUnits = Units.PIXELS;

            var imported = app.open(new File({json.dumps(image_path)}));
            imported.selection.selectAll();
            imported.selection.copy();
            imported.close(SaveOptions.DONOTSAVECHANGES);

            app.activeDocument = doc;
            doc.paste();

            var layer = doc.activeLayer;
            layer.name = {json.dumps(layer_name)};
            layer.translate({dx}, {dy});

            app.preferences.rulerUnits = originalUnits;
            return "success";
        }} catch (e) {{
            return "error: " + e.toString();
        }}
    }})();
    """


def paste(filename: str, layer_name: str, x: int, y: int):
    """Paste `filename` into the active Photoshop document at screen point (x, y).

    Returns None on success, or an error string.
    """
    photoshop = detect_photoshop_name()
    if not photoshop:
        return "Photoshop does not appear to be running"

    abs_path = os.path.abspath(filename)
    if not os.path.exists(abs_path):
        return f"image not found: {abs_path}"

    # Translate the absolute screen point into a document-centre-relative
    # offset, since a freshly pasted layer lands centred in the document.
    screen = get_screen_size()
    if screen:
        screen_width, screen_height = screen
        dx = x - screen_width / 2
        dy = y - screen_height / 2
        logger.info(
            "screen=%sx%s point=(%s, %s) offset=(%.1f, %.1f)",
            screen_width, screen_height, x, y, dx, dy,
        )
    else:
        dx, dy = x, y
        logger.warning("Falling back to raw coordinates - placement may drift")

    jsx = _build_jsx(abs_path, layer_name, dx, dy)

    # Embed the JSX inside an AppleScript string literal.
    escaped = jsx.replace("\\", "\\\\").replace('"', '\\"')
    apple_script = f"""
    tell application {json.dumps(photoshop)}
        activate
        do javascript "{escaped}"
    end tell
    """

    stdout, err = _run_osascript(apple_script, timeout=60)
    if err:
        logger.error("Photoshop paste failed: %s", err)
        return err

    if stdout != "success":
        logger.error("ExtendScript reported: %s", stdout)
        return stdout or "unknown ExtendScript error"

    logger.info("Pasted layer %r into %s", layer_name, photoshop)
    return None
