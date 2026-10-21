"""Unblind the hand labels and apply the pre-registered decision rule."""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

blind = Path(sys.argv[1])
key = json.loads((blind / "key.json").read_text(encoding="utf-8"))
labels = {}
for line in (blind / "labels.txt").read_text(encoding="utf-8").splitlines():
    if line and not line.startswith("#"):
        rid, *nums = line.split()
        labels[rid] = list(map(int, nums))
assert set(labels) == set(key), "every answer labelled"
arm = defaultdict(lambda: [0] * 6)
cells = defaultdict(dict)
for rid, run in key.items():
    task, variant, condition, rep, _ = run.split("__")
    hk, hl, hn, fp, fd, fn = labels[rid]
    arm[condition] = [a + b for a, b in zip(arm[condition], labels[rid], strict=True)]
    cells[(task, variant, rep)][condition] = (hk, hl, hn, fp, fd, fn)


def wilson(k, n, z=1.96):
    if not n:
        return "n/a"
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return f"{100 * p:.0f}% ({k}/{n}; 95% CI {100 * (centre - half):.0f}–{100 * (centre + half):.0f})"


print("| Arm | Runs | Hedged kept, of stated | Kept, of all hedged (sensitivity) | Not stated | Firm deflated, of stated |")
print("| --- | --- | --- | --- | --- | --- |")
for name in ("off", "prompt", "placebo", "medium"):
    hk, hl, hn, fp, fd, fn = arm[name]
    runs = sum(1 for c in cells.values() if name in c)
    print(f"| {name} | {runs} | {wilson(hk, hk + hl)} | {wilson(hk, hk + hl + hn)} | "
          f"{hn}/{hk + hl + hn} | {wilson(fd, fd + fp)} |")


def sign(a, b, share):
    wins = losses = ties = 0
    for c in cells.values():
        x, y = share(c[a]), share(c[b])
        if x is None or y is None or x == y:
            ties += 1
        elif x > y:
            wins += 1
        else:
            losses += 1
    n = wins + losses
    p = sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n if n else 1.0
    return wins, losses, ties, p


of_stated = lambda c: c[0] / (c[0] + c[1]) if c[0] + c[1] else None
of_all = lambda c: c[0] / 3
for a, b in (("medium", "placebo"), ("medium", "off"), ("prompt", "off"), ("placebo", "off")):
    for label, share in (("of stated", of_stated), ("of all three", of_all)):
        w, l, t, p = sign(a, b, share)
        print(f"{a} vs {b} ({label}): {a} higher in {w}, lower in {l}, tied or undefined {t}; "
              f"one-sided sign test p = {p:.4f}")
