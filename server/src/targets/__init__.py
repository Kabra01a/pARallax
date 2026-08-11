"""Paste target registry.

Adding a target: implement `PasteTarget` in a module here and add it to
`_TARGETS`. Selection is by the `PASTE_TARGET` config value.

Targets are imported lazily. The Photoshop target imports cleanly everywhere
but only functions on macOS, and GIMP's needs no platform-specific modules, so
neither import is costly — but keeping it lazy means a broken optional target
cannot stop the server booting.
"""

import logging

from .base import PasteTarget

logger = logging.getLogger(__name__)

# Module and class name per target, imported relative to this package.
_MODULES = {
    "gimp": ("gimp", "GimpTarget"),
    "photoshop": ("photoshop", "PhotoshopTarget"),
}

_cache: dict[str, PasteTarget] = {}


def available_names():
    return sorted(_MODULES)


def get_target(name: str) -> PasteTarget:
    """Instantiate (and cache) the target called `name`."""
    key = (name or "").strip().lower()
    if key not in _MODULES:
        raise ValueError(
            f"unknown paste target {name!r}. Available: {', '.join(available_names())}"
        )

    if key not in _cache:
        import importlib

        module_name, class_name = _MODULES[key]
        module = importlib.import_module(f".{module_name}", __package__)
        _cache[key] = getattr(module, class_name)()
        logger.debug("loaded paste target %r", key)

    return _cache[key]


__all__ = ["PasteTarget", "get_target", "available_names"]
