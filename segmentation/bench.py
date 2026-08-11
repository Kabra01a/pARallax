"""Measure segmentation latency on this machine.

    python bench.py                          # default model, synthetic image
    python bench.py -i photo.jpg -n 20
    python bench.py -m birefnet-general-lite,birefnet-general,u2net

Reports warm-up cost separately from steady-state, and compares the first
third of runs against the last third - on a fanless machine a rising trend
means thermal throttling, which matters more than the headline number.
"""

import argparse
import io
import statistics
import time
from pathlib import Path

from PIL import Image, ImageDraw


def synthetic_image(size=(1024, 1024)) -> bytes:
    """A textured image with a clear foreground subject, for when no photo is given."""
    img = Image.new("RGB", size, (32, 44, 60))
    draw = ImageDraw.Draw(img)
    for i in range(0, size[0], 24):
        draw.line([(i, 0), (i, size[1])], fill=(44, 58, 78), width=1)
    cx, cy = size[0] // 2, size[1] // 2
    draw.ellipse([cx - 220, cy - 260, cx + 220, cy + 260], fill=(214, 132, 74))
    draw.ellipse([cx - 90, cy - 200, cx + 90, cy - 40], fill=(240, 200, 160))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def downscale(payload: bytes, longest_side: int) -> bytes:
    """Shrink so the longest side is `longest_side`, preserving aspect ratio."""
    with Image.open(io.BytesIO(payload)) as img:
        img = img.convert("RGB")
        img.thumbnail((longest_side, longest_side), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()


def bench_model(name: str, payload: bytes, runs: int, post_process: bool = True,
                providers=None):
    from rembg import remove

    print(f"\n  {name}")

    import session as session_factory

    t0 = time.time()
    session, actual = session_factory.create_session(name)
    load_ms = (time.time() - t0) * 1000
    print(f"    providers      {', '.join(actual)}")

    t0 = time.time()
    remove(payload, session=session, only_mask=True, post_process_mask=post_process)
    warmup_ms = (time.time() - t0) * 1000

    print(f"    session load   {load_ms:8.0f} ms")
    print(f"    first inference{warmup_ms:8.0f} ms  (includes graph warm-up)")

    times = []
    for i in range(runs):
        t0 = time.time()
        remove(payload, session=session, only_mask=True, post_process_mask=post_process)
        times.append((time.time() - t0) * 1000)
        print(f"      run {i + 1:2d}/{runs}  {times[-1]:7.0f} ms", end="\r", flush=True)
    print(" " * 40, end="\r")

    times_sorted = sorted(times)
    p95 = times_sorted[max(0, int(len(times_sorted) * 0.95) - 1)]
    print(f"    median         {statistics.median(times):8.0f} ms")
    print(f"    p95            {p95:8.0f} ms")
    print(f"    min / max      {min(times):8.0f} / {max(times):.0f} ms")

    if runs >= 6:
        third = max(1, runs // 3)
        early = statistics.median(times[:third])
        late = statistics.median(times[-third:])
        drift = (late - early) / early * 100 if early else 0
        verdict = "steady" if abs(drift) < 15 else "THROTTLING - sustained use will be slower"
        print(f"    drift          {drift:+7.1f} %  first third vs last third ({verdict})")

    return {"model": name, "median": statistics.median(times), "p95": p95}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-i", "--image", help="path to a test image (default: synthetic)")
    parser.add_argument("-m", "--models", default="birefnet-general-lite",
                        help="comma-separated rembg model names")
    parser.add_argument("-n", "--runs", type=int, default=10)
    parser.add_argument("-r", "--resize", type=int, metavar="PX",
                        help="downscale the test image so its longest side is PX. "
                             "The app uploads 256px crops, so bench that, not a 12MP photo.")
    parser.add_argument("--no-post-process", action="store_true",
                        help="disable morphological mask cleanup (costly at high resolution)")
    parser.add_argument("-p", "--providers", default="auto",
                        help="'auto' (prefer CoreML/CUDA), 'cpu', or an explicit "
                             "comma-separated ONNX Runtime provider list")
    args = parser.parse_args()

    if args.image:
        payload = Path(args.image).read_bytes()
        source = args.image
    else:
        payload = synthetic_image()
        source = "synthetic 1024x1024"

    if args.resize:
        payload = downscale(payload, args.resize)
        source += f" (downscaled to {args.resize}px)"

    with Image.open(io.BytesIO(payload)) as probe:
        dims = f"{probe.size[0]}x{probe.size[1]}"

    print(f"image: {source} ({dims}, {len(payload) / 1024:.0f} KB)")
    print(f"runs:  {args.runs} per model after one warm-up")
    print(f"post-process mask: {not args.no_post_process}")

    import onnxruntime as ort
    print(f"onnxruntime {ort.__version__}, available providers: "
          f"{', '.join(ort.get_available_providers())}")

    import config
    config.PROVIDERS = args.providers
    providers = config.resolve_providers()

    results = []
    for name in [m.strip() for m in args.models.split(",") if m.strip()]:
        try:
            results.append(bench_model(name, payload, args.runs,
                                       post_process=not args.no_post_process,
                                       providers=providers))
        except Exception as exc:
            print(f"\n  {name}\n    FAILED: {exc}")

    if len(results) > 1:
        print("\nsummary (median, fastest first)")
        for r in sorted(results, key=lambda r: r["median"]):
            print(f"  {r['model']:26s} {r['median']:7.0f} ms   p95 {r['p95']:.0f} ms")

    if results:
        best = min(results, key=lambda r: r["median"])["median"]
        print(f"\nA cut round-trip will cost roughly {best / 1000:.1f}s plus network.")
        if best > 2000:
            print("Over ~2s stops feeling interactive - try birefnet-general-lite,")
            print("a smaller input size, or ONNX Runtime with the CoreML provider.")


if __name__ == "__main__":
    main()
