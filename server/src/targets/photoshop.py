"""Adobe Photoshop paste target (macOS).

Drives Photoshop via AppleScript's `do javascript`, which executes an
ExtendScript payload inside the running application. This route does NOT need
the Photoshop "Remote Connection" password - that is only required for the
socket-based protocol the upstream project used.

Requires a licensed desktop Photoshop. The web and Express tiers expose no
scripting interface, so they cannot work. Use the GIMP target instead.

STATUS: supported but currently unverified. The surrounding code was refactored
into the PasteTarget interface (paste() became a method and gained the
screen_size argument) without a licensed Photoshop available to re-test against.
The AppleScript and ExtendScript themselves are unchanged from the working
version. Re-run `python server/tools/check_target.py photoshop` to confirm.

macOS-only by nature. A UXP plugin would make it cross-platform; see the
roadmap in the top-level README.
"""

import json
import logging
import os
import subprocess
from functools import lru_cache

import config

from .base import PasteTarget

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


class PhotoshopTarget(PasteTarget):
    name = "photoshop"
    display_name = "Adobe Photoshop"

    def is_available(self):
        photoshop = detect_photoshop_name()
        if not photoshop:
            return False, ("no running Photoshop process found — open Photoshop "
                           "with a document, or set PHOTOSHOP_APP_NAME")
        size = get_screen_size()
        detail = f"{photoshop}"
        if size:
            detail += f", screen {size[0]}x{size[1]}"
        return True, detail

    def screen_size(self):
        return get_screen_size()

    def paste(self, image_path: str, layer_name: str, x: int, y: int,
              screen_size=None):
        """Paste into the active Photoshop document near screen point (x, y).

        Returns None on success, or an error string.
        """
        photoshop = detect_photoshop_name()
        if not photoshop:
            return "Photoshop does not appear to be running"

        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            return f"image not found: {abs_path}"

        # A freshly pasted layer lands centred in the document, so translate the
        # absolute screen point into an offset from the centre.
        screen = screen_size or get_screen_size()
        if screen:
            dx = x - screen[0] / 2
            dy = y - screen[1] / 2
            logger.info("screen=%sx%s point=(%s, %s) offset=(%.1f, %.1f)",
                        screen[0], screen[1], x, y, dx, dy)
        else:
            dx, dy = x, y
            logger.warning("no screen size available - placement may drift")

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

        logger.info("pasted layer %r into %s", layer_name, photoshop)
        return None
