# pARallax — segmentation service

Takes an image, returns a saliency mask. This is the piece that makes `/cut`
work, and it replaces the public U²-Net endpoint the upstream project relied on
in 2020 (which is no longer dependable).

Runs via [rembg](https://github.com/danielgatis/rembg) with a **two-tier** model
choice, because measurement forced the issue:

| Tier | Model | Latency | Use |
|---|---|---|---|
| **Fast** | `u2net` (default) | ~750 ms | Interactive press-and-hold |
| **Quality** | `birefnet-general-lite` | ~10 s | Better edges, when you can wait |

Set `MODEL_NAME` to switch. Full numbers in
[Measured results](#measured-results). All default models are MIT or Apache
licensed and safe to redistribute with this project.

## Why BiRefNet is available but not the default

BiRefNet's bilateral reference mechanism cross-checks fine local detail against
global context across several refinement passes. In practice that means visibly
better edges on the cases BASNet struggled with: hair, fur, semi-transparent
fabric, and thin structures like railings or bicycle spokes.

A note on **RMBG-2.0**, which benchmarks higher: it's licensed CC BY-NC 4.0, so
commercial use requires a paid agreement with BRIA. pARallax is MIT, and shipping
a non-commercial model inside an MIT project would create a licence conflict for
anyone who clones it. It's available as `bria-rmbg` if you want it for personal
experiments — the service logs a loud warning when selected.

## Setup

> **Python 3.10–3.12 required.** `onnxruntime` — the engine rembg runs models on
> — publishes no wheels for CPython 3.13 or 3.14, so `pip install` fails outright
> on a newer interpreter. Check with `python3 --version`; if it's 3.13+, install
> 3.12 (`brew install python@3.12`) and point the venv at it explicitly.

```bash
cd segmentation
python3.12 -m venv venv          # or /opt/homebrew/bin/python3.12
source venv/bin/activate
python --version                 # confirm 3.12.x before installing
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env      # optional, defaults are sensible
```

## Run

```bash
python service.py
```

Listens on `:8081`, which is the local server's default
`SEGMENTATION_SERVICE_URL`, so the two connect with no configuration.

> The **first inference downloads model weights** to `~/.u2net/` — expect a
> long first request. Use `--preload` to pay that cost at startup instead:
>
> ```bash
> python service.py --preload
> ```

## Verify

```bash
curl http://localhost:8081/                       # health + active model

curl -F "data=@photo.jpg" http://localhost:8081/ -o mask.png      # grayscale mask
curl -F "data=@photo.jpg" http://localhost:8081/cutout -o cut.png # RGBA cutout
```

`cutout` is the one to eyeball — open `cut.png` and look at the edges.

The response carries `X-Inference-Ms`, so you can watch real latency per request
without instrumenting anything.

## Measure performance

Latency decides whether cutting feels instant or sluggish, and it varies wildly
by machine. Measure yours:

```bash
python bench.py                                  # default model, synthetic image
python bench.py -i photo.jpg -n 20               # your own image, 20 runs
python bench.py -m birefnet-general-lite,birefnet-general,u2net -n 10
```

Reports median and p95 separately from warm-up, and compares the first third of
runs against the last third. On a fanless machine a rising trend means thermal
throttling — worth knowing before you blame the model.

## Measured results

Measured on a **MacBook Air (Apple Silicon, 16 GB, fanless)**, macOS,
onnxruntime 1.28.0, CPU execution provider, `post_process_mask=true`.
Reproduce with `bench.py`.

### Latency

| Model | Network input | Median | Verdict |
|---|---|---|---|
| `u2net` | 320×320 | **748 ms** | Interactive |
| `birefnet-general-lite` | 1024×1024 | 10,204 ms | Too slow for a gesture |
| `birefnet-general` | 1024×1024 | 23,369 ms | Batch use only |

BiRefNet gives visibly better edges — the test subject was polished steel, a case
the original project documented as a failure mode, and it was cleanly segmented.
But at **14× the cost**, it cannot back a press-and-hold interaction on this
hardware. Hence the two tiers.

### Input resolution does not matter

Same model, same machine, varying the uploaded image:

| Uploaded image | Median |
|---|---|
| 192×256 (12 KB) | 11,406 ms |
| 768×1024 (117 KB) | 10,204 ms |
| 3072×4096 (2.6 MB) | 12,752 ms |
| 3072×4096, no post-processing | 11,279 ms |

Feeding a 12 KB thumbnail costs the same as a 12-megapixel photo, because rembg
resizes everything to the model's fixed input — 1024×1024 for BiRefNet — before
inference. Shrinking uploads is not an optimization. Mask post-processing at
12 MP costs ~1.5s and *is* worth disabling for large inputs.

### CoreML acceleration does not work with BiRefNet

Worth documenting because it looks like the obvious win and isn't.

Two separate problems:

1. **rembg never tries.** Its provider selection checks only for CUDA and ROCM,
   then falls back to `["CPUExecutionProvider"]`. On Apple Silicon the GPU and
   Neural Engine sit idle. `session.py` overrides this — that part works.

2. **BiRefNet's graph will not compile.** With CoreML actually requested,
   ONNX Runtime fails:

   ```
   Error compiling model: Failed to parse the model specification.
   Unable to parse ML Program: in operation
     /squeeze_module/squeeze_module.0/dec_att/aspp_deforms.2/atrous_conv/Conv:
   Required param 'pad' is missing
   ```

   The dilated convolution in BiRefNet's ASPP decoder is not expressed in a way
   CoreML's MLProgram parser accepts. This is not a tuning problem.

Also of note: `ANECompilerService` runs during MLProgram compilation **regardless
of `MLComputeUnits`**, and it is expensive — observed at 100% of a core for
extended periods, with heavy swap. If you experiment with CoreML here, watch for
it in Activity Monitor.

`session.py` degrades through accelerated-with-options → accelerated → CPU, so a
failure like this is logged rather than fatal.

### Benchmarking notes

Two mistakes that produced garbage numbers, recorded so they aren't repeated:

- **Concurrent runs.** Three `bench.py` processes running at once inflated a
  measurement by ~48%, which was initially misread as thermal throttling. Check
  `pgrep -fl bench.py` before trusting any result.
- **Ctrl+C is not always enough.** Backgrounded runs survive it. Verify with
  `pgrep`, then `pkill -f bench.py`.

## Models

Set with `MODEL_NAME` in `.env`, or `--model` on the command line.

| Name | Notes | Licence |
|---|---|---|
| `birefnet-general-lite` | **Default.** `swin_v1_tiny` backbone, ~4× faster and ~5× smaller than full | MIT |
| `birefnet-general` | Best quality, slowest | MIT |
| `birefnet-portrait` | Tuned for people | MIT |
| `birefnet-dis` | Dichotomous image segmentation | MIT |
| `birefnet-hrsod` | High-resolution salient object detection | MIT |
| `birefnet-cod` | Concealed object detection | MIT |
| `birefnet-massive` | Trained on a larger dataset | MIT |
| `isnet-general-use` | Lighter fallback, between U²-Net and BiRefNet | MIT |
| `u2net` | The 2020 baseline — keep for comparison benchmarks | Apache 2.0 |
| `u2netp` | Tiny U²-Net (~4 MB), useful for smoke tests | Apache 2.0 |
| `silueta` | U²-Net reduced to 43 MB | Apache 2.0 |
| `bria-rmbg` | Higher quality, **non-commercial only** | CC BY-NC 4.0 |

## API

| Method | Route | Body | Returns |
|---|---|---|---|
| `GET` | `/` or `/ping` | — | JSON health, active model, load state |
| `POST` | `/` | multipart `data` | `image/png`, grayscale mask |
| `POST` | `/cutout` | multipart `data` | `image/png`, RGBA cutout |

`POST /` is what `server/src/main.py` calls. `data` is the expected field name;
`file` and `image` are accepted as aliases for convenience with curl.

Errors return `{"status": "error", "error": "..."}` with a 4xx or 5xx status.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_NAME` | `birefnet-general-lite` | Which model to load |
| `POST_PROCESS_MASK` | `true` | Morphological cleanup — cheap, usually worth it |
| `ALPHA_MATTING` | `false` | Better edges on hair, but slow on CPU. Measure first |
| `ALPHA_MATTING_FG_THRESHOLD` | `240` | Foreground confidence cutoff |
| `ALPHA_MATTING_BG_THRESHOLD` | `10` | Background confidence cutoff |
| `ALPHA_MATTING_ERODE_SIZE` | `10` | Erosion before matting |
| `HOST` / `PORT` | `0.0.0.0` / `8081` | Bind address |
| `DEBUG` | `false` | Verbose logging |

## Troubleshooting

**First request hangs for minutes** — it's downloading weights. Watch
`~/.u2net/`. Use `--preload` next time.

**`pip install` says "no matching distribution" for onnxruntime** — your Python
is 3.13 or newer. See the version note under Setup.

**Download fails** — weights come from GitHub release assets. Behind a
restrictive proxy this is blocked; download manually into `~/.u2net/`.

**Slower than expected** — try `birefnet-general-lite`, confirm
`ALPHA_MATTING=false`, and run `bench.py` to check whether you're throttling.
Note that rembg selects execution providers itself and only checks for CUDA and
ROCM, so on Apple Silicon it runs CPU-only; this service overrides that (see
`session.py`).

**Hangs on startup with `ANECompilerService` at 100% CPU** — CoreML is trying to
compile the graph for the Neural Engine. On BiRefNet this was measured consuming
48 minutes of CPU and ~11 GB of swap without completing. `COREML_COMPUTE_UNITS`
defaults to `CPUAndGPU` to avoid it. If you set it to `ALL` or
`CPUAndNeuralEngine`, expect this.

**Fanless machines throttle hard.** Repeated 1024×1024 inference degraded
measured latency by ~48% for identical work on a MacBook Air. Let the machine
idle between benchmark runs or the numbers are meaningless.

**Mask is empty or inverted** — confirm you're reading the right endpoint. `/`
returns a mask (white = subject), `/cutout` returns the composited RGBA.
