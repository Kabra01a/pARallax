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


def main() -> int:
    target = GimpTarget()

    if len(sys.argv) > 1:
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
