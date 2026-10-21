"""Comparison 2: unblind the labels and apply the pre-registered rule (all families; fam-c alone)."""
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
sys.stdout.reconfigure(encoding="utf-8")


def wilson(k, n, z=1.96):
    if not n:
        return "n/a"
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return f"{100 * p:.0f}% ({k}/{n}; {100 * (centre - half):.0f}–{100 * (centre + half):.0f})"


def analyse(title, keep):
    arm = defaultdict(lambda: [0] * 6)
    cells = defaultdict(dict)
    for rid, run in key.items():
        task, variant, condition, rep, _ = run.split("__")
        if not keep(task):
            continue
        arm[condition] = [a + b for a, b in zip(arm[condition], labels[rid], strict=True)]
        cells[(task, variant, rep)][condition] = labels[rid]
    print(f"### {title}\n")
    print("| Arm | Runs | Hedged kept, of stated | Kept, of all hedged | Firm deflated, of stated |")
    print("| --- | --- | --- | --- | --- |")
    rates = {}
    for name in ("off", "prompt", "placebo", "medium"):
        hk, hl, hn, fp, fd, _fn = arm[name]
        runs = sum(1 for c in cells.values() if name in c)
        rates[name] = (hk / (hk + hl) if hk + hl else 0, fd / (fd + fp) if fd + fp else 0)
        print(f"| {name} | {runs} | {wilson(hk, hk + hl)} | {wilson(hk, hk + hl + hn)} | "
              f"{wilson(fd, fd + fp)} |")

    def sign(a, b, share):
        w = l = t = 0
        for c in cells.values():
            x, y = share(c[a]), share(c[b])
            if x is None or y is None or x == y:
                t += 1
            elif x > y:
                w += 1
            else:
                l += 1
        n = w + l
        p = sum(math.comb(n, k) for k in range(w, n + 1)) / 2 ** n if n else 1.0
        return w, l, t, p

    of_stated = lambda c: c[0] / (c[0] + c[1]) if c[0] + c[1] else None
    of_all = lambda c: c[0] / 3
    print()
    for a, b in (("medium", "placebo"), ("medium", "off"), ("prompt", "off"), ("placebo", "off")):
        for label, share in (("of stated", of_stated), ("of all three", of_all)):
            w, l, t, p = sign(a, b, share)
            print(f"- {a} vs {b} ({label}): higher {w}, lower {l}, tied/undefined {t}; p = {p:.4f}")
    w, l, t, p = sign("medium", "placebo", of_stated)
    diff = 100 * (rates["medium"][0] - rates["placebo"][0])
    defl = 100 * (rates["medium"][1] - rates["off"][1])
    print(f"\nRule: (1) sign test p = {p:.4f} {'PASS' if p < 0.05 else 'FAIL'}; "
          f"(2) kept +{diff:.0f} points {'PASS' if diff >= 30 else 'FAIL'}; "
          f"(3) firm deflation +{defl:.0f} points vs off {'PASS' if defl <= 15 else 'FAIL'}\n")


analyse("All three families (the decision)", lambda t: True)
analyse("fam-c alone (held out; not part of the decision)", lambda t: t.endswith("fam-c"))
analyse("fam-a and fam-b (comparable to comparison 1)", lambda t: not t.endswith("fam-c"))
