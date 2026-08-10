"""Diagnostic: verify the Photoshop integration end to end.

    python server/tools/check_photoshop.py

Detects the running Photoshop, then pastes a small test swatch into the
active document.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import logging  # noqa: E402

from PIL import Image  # noqa: E402

import ps  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


def main() -> int:
    name = ps.detect_photoshop_name()
    if not name:
        print("FAIL: no running Photoshop process found.")
        print("      Open Photoshop with a document, or set PHOTOSHOP_APP_NAME.")
        return 1
    print(f"OK:   detected {name}")

    size = ps.get_screen_size()
    print(f"OK:   screen size {size}" if size else "WARN: could not read screen size")

    tmp = Path(__file__).resolve().parent.parent / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    swatch = tmp / "_photoshop_check.png"
    Image.new("RGBA", (120, 120), (220, 60, 60, 255)).save(swatch)

    err = ps.paste(str(swatch), "photoshop-check", 0, 0)
    swatch.unlink(missing_ok=True)

    if err:
        print(f"FAIL: {err}")
        return 1

    print("OK:   pasted test layer 'photoshop-check' - delete it when done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
