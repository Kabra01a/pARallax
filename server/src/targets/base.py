"""Paste target interface.

A target receives a transparent PNG and places it into some editing surface at
a position derived from where the camera was pointed. Implementations live
alongside this file and are registered in `__init__.py`.

Targets are deliberately thin: locating the screen position is the local
server's job (see screenpoint.py); a target only has to place a layer.

On coordinate spaces — the one genuinely fiddly part. `screenpoint` returns an
absolute *screen* pixel, but an editor positions layers within its *document*.
Those spaces differ, and the mapping depends on window position and zoom, which
we cannot see. So `paste()` receives both the absolute point and the screen
size, and each target maps as best it can:

  * Photoshop offsets the pasted layer relative to the document centre, since a
    fresh paste lands centred.
  * GIMP places the layer at the same *fraction* of the canvas as the pointed
    fraction of the screen — point top-left, land top-left.

Neither is pixel-exact. Making it exact needs the editor to report its canvas
rect on screen, which is future work.
"""

from abc import ABC, abstractmethod


class PasteTarget(ABC):
    """Something pARallax can paste a cutout into."""

    #: Short identifier used by the PASTE_TARGET config value.
    name: str = ""

    #: Human-readable name for logs and the /ping payload.
    display_name: str = ""

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Return (available, detail).

        `detail` explains what was found, or why not — it goes straight into
        diagnostics, so make it actionable.
        """

    @abstractmethod
    def paste(self, image_path: str, layer_name: str, x: int, y: int,
              screen_size: tuple[int, int] | None = None):
        """Place `image_path` according to screen point (x, y).

        `screen_size` is (width, height) of the display the point came from, or
        None if unknown. Returns None on success, or an error string.
        """

    def screen_size(self):
        """Return (width, height) of the display, or None if unknown.

        Override where the target can report this more accurately than the
        caller can.
        """
        return None
