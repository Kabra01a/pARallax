"""Discover which PDB procedures your GIMP actually has, and what they return.

    python server/tools/gimp_probe.py            # full capability report
    python server/tools/gimp_probe.py '(gimp-version)'   # evaluate one expression

GIMP renamed and restructured much of the PDB across 2.10, 3.0 and 3.2:
procedures were renamed (`gimp-image-list` became `gimp-get-images`,
`gimp-image-width` became `gimp-image-get-width`) and array returns lost their
separate length. Rather than guess a version, this asks.

Binding is tested by evaluating the bare symbol, which has no side effects — an
unbound name raises "unbound variable", a bound one returns a closure.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targets.gimp import GimpTarget  # noqa: E402

# Candidates per capability, newest naming first.
CANDIDATES = {
    "list images": ["gimp-get-images", "gimp-image-list"],
    "image width": ["gimp-image-get-width", "gimp-image-width"],
    "image height": ["gimp-image-get-height", "gimp-image-height"],
    "layer width": ["gimp-drawable-get-width", "gimp-drawable-width"],
    "layer height": ["gimp-drawable-get-height", "gimp-drawable-height"],
    "load as layer": ["gimp-file-load-layer"],
    "insert layer": ["gimp-image-insert-layer"],
    "set item name": ["gimp-item-set-name", "gimp-layer-set-name"],
    "set offsets": ["gimp-layer-set-offsets"],
    "flush displays": ["gimp-displays-flush"],
}


def is_bound(target, name) -> bool:
    """Evaluate the bare symbol — no call, so no side effects."""
    try:
        target.evaluate(name)
        return True
    except Exception as exc:
        return "unbound" not in str(exc).lower()


def list_images(target) -> int:
    """Show every open image and its layers.

    Diagnoses the "GIMP said it pasted but I cannot see it" case: the paste goes
    to whichever image the lister returns first, which is not necessarily the
    one displayed on screen.
    """
    procs = target.procs()
    lister = procs["images"]

    raw = target.evaluate(f"({lister})")
    print(f"({lister}) -> {raw}\n")

    ids = target.evaluate(
        f"""(let* ((raw ({lister}))
       (v (cond ((vector? raw) raw)
                ((and (pair? raw) (vector? (car raw))) (car raw))
                ((and (pair? raw) (pair? (cdr raw)) (vector? (cadr raw))) (cadr raw))
                (else #()))))
  (vector->list v))"""
    )
    print(f"open image ids: {ids}")

    numbers = [int(n) for n in __import__("re").findall(r"\d+", ids)]
    if not numbers:
        print("no images open")
        return 1

    for index, image_id in enumerate(numbers):
        try:
            w = target.evaluate(f"(car ({procs['image_w']} {image_id}))")
            h = target.evaluate(f"(car ({procs['image_h']} {image_id}))")
            layers = target.evaluate(
                f"""(let ((ls (gimp-image-get-layers {image_id})))
  (map (lambda (l) (car (gimp-item-get-name l)))
       (vector->list (if (vector? ls) ls (car ls)))))"""
            )
            marker = "  <- index 0, this is where pARallax pastes" if index == 0 else ""
            print(f"\n  image {image_id}: {w}x{h}{marker}")
            print(f"    layers (top first): {layers}")
        except Exception as exc:
            print(f"\n  image {image_id}: could not inspect - {exc}")

    if len(numbers) > 1:
        print(f"\n{len(numbers)} images are open. pARallax pastes into image "
              f"{numbers[0]}. If that is not the one on screen, close the others "
              f"or bring the right one forward.")
    return 0


def main() -> int:
    target = GimpTarget()

    if len(sys.argv) > 1:
        if sys.argv[1] in ("--images", "-i"):
            try:
                return list_images(target)
            except Exception as exc:
                print(f"ERROR: {exc}")
                return 1
        try:
            print(target.evaluate(sys.argv[1]))
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 1

    try:
        version = target.version()
    except Exception as exc:
        print(f"cannot reach GIMP: {exc}")
        return 1

    print(f"GIMP {version} at {target.host}:{target.port}\n")
    print("bound procedures")

    found = {}
    for capability, names in CANDIDATES.items():
        winner = next((n for n in names if is_bound(target, n)), None)
        found[capability] = winner
        mark = "ok  " if winner else "MISS"
        detail = winner or f"none of: {', '.join(names)}"
        print(f"  [{mark}] {capability:16s} {detail}")

    lister = found.get("list images")
    if not lister:
        print("\nNo way to enumerate images — cannot continue.")
        return 1

    print(f"\nreturn shape of ({lister})")
    for label, expr in [
        ("raw", f"({lister})"),
        ("vector?", f"(vector? ({lister}))"),
        ("pair?", f"(pair? ({lister}))"),
        ("vector-length", f"(if (vector? ({lister})) (vector-length ({lister})) -1)"),
        ("list length", f"(if (pair? ({lister})) (length ({lister})) -1)"),
        ("car", f"(if (pair? ({lister})) (car ({lister})) 'not-a-pair)"),
    ]:
        try:
            print(f"  {label:14s} -> {target.evaluate(expr)}")
        except Exception as exc:
            print(f"  {label:14s} -> ERROR: {str(exc)[:80]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
