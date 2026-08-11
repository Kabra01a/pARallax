"""Configuration for the segmentation service. All values env-overridable."""

import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)


def _env(name, default=None):
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name, default):
    try:
        return int(_env(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name, default=False):
    return str(_env(name, str(default))).lower() in ("1", "true", "yes")


# --- Model ----------------------------------------------------------------
# Two tiers, because measured latency forced the issue (see README > Measured
# results). The models differ mainly in the resolution they run at, and that
# resolution dominates cost:
#
#   FAST     u2net                  320x320    ~750 ms on an M-series CPU
#   QUALITY  birefnet-general-lite  1024x1024  ~10-12 s on the same CPU
#            birefnet-general       1024x1024  ~23 s
#
# u2net is the default so the press-and-hold gesture stays responsive. Set
# MODEL_NAME to a birefnet variant when edge quality matters more than speed -
# fine detail like hair, fur and semi-transparent fabric is visibly better.
MODEL_NAME = _env("MODEL_NAME", "u2net")

# Models grouped by intended use, for documentation and the health endpoint.
FAST_MODELS = ("u2net", "u2netp", "silueta", "u2net_human_seg")
QUALITY_MODELS = ("birefnet-general", "birefnet-general-lite", "birefnet-portrait",
                  "birefnet-dis", "birefnet-hrsod", "birefnet-cod", "birefnet-massive")


def model_tier(name=None):
    name = name or MODEL_NAME
    if name in FAST_MODELS:
        return "fast"
    if name in QUALITY_MODELS:
        return "quality"
    return "other"

# Models that are NOT free for commercial use. Selecting one of these is
# allowed but warned about loudly, because this project ships under MIT.
RESTRICTED_MODELS = {
    "bria-rmbg": "CC BY-NC 4.0 - non-commercial only, commercial use needs a "
                 "paid agreement with BRIA",
}

# --- Inference ------------------------------------------------------------
# Morphological cleanup of the mask. Cheap, usually worth it.
POST_PROCESS_MASK = _env_bool("POST_PROCESS_MASK", True)

# Alpha matting refines edges further but costs significant time on CPU.
# Off by default; measure before enabling.
ALPHA_MATTING = _env_bool("ALPHA_MATTING", False)
ALPHA_MATTING_FG_THRESHOLD = _env_int("ALPHA_MATTING_FG_THRESHOLD", 240)
ALPHA_MATTING_BG_THRESHOLD = _env_int("ALPHA_MATTING_BG_THRESHOLD", 10)
ALPHA_MATTING_ERODE_SIZE = _env_int("ALPHA_MATTING_ERODE_SIZE", 10)

# --- Execution providers --------------------------------------------------
# rembg's own provider selection only ever checks for CUDA and ROCM, so on
# macOS it silently falls back to CPU only - leaving the GPU and Neural Engine
# idle. We select providers ourselves and pass them through.
#
# "auto"  prefer CoreML on macOS, then CUDA, then CPU
# "cpu"   force CPU (useful as a benchmark baseline)
# or an explicit comma-separated list of ONNX Runtime provider names.
PROVIDERS = _env("PROVIDERS", "auto")

# CoreML compiles a graph per input shape on first use, so the first inference
# is slow and later ones are fast. BiRefNet's fixed 1024x1024 input means that
# cost is paid exactly once.
PREFERRED_PROVIDERS = ("CoreMLExecutionProvider", "CUDAExecutionProvider")

# Where CoreML stores its compiled graphs. Without this, the multi-minute
# compile is repeated on every process start.
COREML_CACHE_DIR = Path(_env("COREML_CACHE_DIR", Path.home() / ".u2net" / "coreml-cache"))

# ALL | CPUAndGPU | CPUAndNeuralEngine | CPUOnly
#
# Note: this does NOT control whether ANECompilerService runs. Measured on
# macOS with onnxruntime 1.28, ORT invokes that compiler while building an
# MLProgram regardless of the compute units requested, and it is expensive.
# CPUAndGPU is kept as the default only because it is the narrower request.
#
# For BiRefNet specifically, CoreML never gets as far as running: compilation
# fails while parsing the ASPP decoder's atrous convolution. See README.
COREML_COMPUTE_UNITS = _env("COREML_COMPUTE_UNITS", "CPUAndGPU")

# MLProgram is the modern format and generally faster; NeuralNetwork is legacy
# but occasionally compiles when MLProgram will not.
COREML_MODEL_FORMAT = _env("COREML_MODEL_FORMAT", "MLProgram")

# --- Server ---------------------------------------------------------------
HOST = _env("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8081)
DEBUG = _env_bool("DEBUG", False)


def resolve_providers():
    """Return the ONNX Runtime provider list to use, honouring PROVIDERS."""
    import onnxruntime as ort

    available = ort.get_available_providers()

    if PROVIDERS.lower() == "cpu":
        return ["CPUExecutionProvider"]

    if PROVIDERS.lower() != "auto":
        requested = [p.strip() for p in PROVIDERS.split(",") if p.strip()]
        missing = [p for p in requested if p not in available]
        if missing:
            logger.warning("requested providers not available: %s", ", ".join(missing))
            logger.warning("available: %s", ", ".join(available))
        chosen = [p for p in requested if p in available]
        return chosen or ["CPUExecutionProvider"]

    chosen = [p for p in PREFERRED_PROVIDERS if p in available]
    chosen.append("CPUExecutionProvider")

    if len(chosen) == 1:
        logger.warning(
            "no hardware acceleration provider found - running on CPU. "
            "Available: %s", ", ".join(available)
        )
    else:
        logger.info("acceleration: %s", chosen[0])

    return chosen


def warn_if_restricted_model():
    """Log a prominent warning if the selected model is licence-restricted."""
    note = RESTRICTED_MODELS.get(MODEL_NAME)
    if note:
        logger.warning("=" * 72)
        logger.warning("MODEL %r IS LICENCE-RESTRICTED", MODEL_NAME)
        logger.warning("  %s", note)
        logger.warning("  pARallax ships under MIT. Do not redistribute this")
        logger.warning("  model with the project or use it commercially.")
        logger.warning("=" * 72)
