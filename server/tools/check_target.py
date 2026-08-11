"""Diagnostic: verify the configured paste target end to end.

    python server/tools/check_target.py            # uses PASTE_TARGET
    python server/tools/check_target.py gimp
    python server/tools/check_target.py photoshop

Detects the editor, reports what it found, then pastes a small test swatch so
you can see with your own eyes that the bridge works.
"""

import logging
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import config  # noqa: E402
import targets  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


def make_swatch(path: Path):
    """A recognisable test image with transparency, so alpha is exercised."""
    img = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([10, 10, 230, 230], fill=(220, 60, 60, 255))
    draw.ellipse([80, 80, 160, 160], fill=(0, 0, 0, 0))
    img.save(path)


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else config.PASTE_TARGET

    try:
        target = targets.get_target(name)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1

    print(f"target: {target.display_name} ({target.name})")

    ready, detail = target.is_available()
    if not ready:
        print(f"FAIL: {detail}")
        return 1
    print(f"OK:   {detail}")

    size = target.screen_size()
    print(f"OK:   screen size {size}" if size
          else "note: target cannot report screen size; the server supplies it")

    tmp = SRC.parent / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    swatch = tmp / "_target_check.png"
    make_swatch(swatch)

    # Centre of a nominal 1440x900 screen, so placement lands mid-canvas.
    err = target.paste(str(swatch), "parallax-check", 720, 450,
                       screen_size=(1440, 900))
    swatch.unlink(missing_ok=True)

    if err:
        print(f"FAIL: {err}")
        return 1

    print("OK:   pasted a red ring as layer 'parallax-check'.")
    print("      Look for it in the editor, then delete the layer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
