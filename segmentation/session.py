"""Session creation with hardware acceleration and graceful degradation.

rembg picks execution providers itself and only ever looks for CUDA and ROCM,
so on Apple Silicon it silently runs CPU-only. This module selects providers
explicitly, passes CoreML tuning options, and falls back cleanly when any of
that is unsupported — a wrong provider option should never be fatal.
"""

import logging

import config

logger = logging.getLogger(__name__)


def _coreml_options() -> dict:
    """Provider options for the CoreML execution provider.

    `ModelCacheDirectory` is the important one. CoreML compiles the ONNX graph
    into its own format on first use, which takes minutes for a model this
    size. Caching means that cost is paid once rather than on every start.
    """
    return {
        "ModelFormat": config.COREML_MODEL_FORMAT,
        "MLComputeUnits": config.COREML_COMPUTE_UNITS,
        "ModelCacheDirectory": str(config.COREML_CACHE_DIR),
        "RequireStaticInputShapes": "0",
    }


def _provider_specs():
    """Providers in ONNX Runtime form, with options attached where useful."""
    specs = []
    for name in config.resolve_providers():
        if name == "CoreMLExecutionProvider":
            config.COREML_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            specs.append((name, _coreml_options()))
        else:
            specs.append(name)
    return specs


def create_session(model_name: str):
    """Build a rembg session, degrading rather than failing.

    Order of attempts:
      1. accelerated providers with tuning options
      2. same providers, no options   (in case an option key is unsupported)
      3. CPU only                     (always works)
    """
    from rembg import new_session

    attempts = [
        ("accelerated + options", _provider_specs()),
        ("accelerated", config.resolve_providers()),
        ("cpu", ["CPUExecutionProvider"]),
    ]

    # Deduplicate: if resolve_providers() already returned CPU-only, the first
    # two attempts are identical and there is nothing to fall back from.
    seen = []
    for label, providers in attempts:
        key = repr(providers)
        if key in seen:
            continue
        seen.append(key)

        names = [p[0] if isinstance(p, tuple) else p for p in providers]
        try:
            session = new_session(model_name, providers=providers)
            active = session.inner_session.get_providers()

            # ORT silently drops providers it cannot honour, so report what we
            # actually got rather than what we asked for.
            if "CoreMLExecutionProvider" in names and \
                    "CoreMLExecutionProvider" not in active:
                logger.warning("CoreML was requested but ONNX Runtime is not using it")

            logger.info("session ready via %s: %s", label, ", ".join(active))
            return session, active

        except Exception as exc:
            logger.warning("provider attempt %r failed: %s", label, exc)

    raise RuntimeError(f"could not create a session for {model_name!r}")
