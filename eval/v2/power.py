"""How big the confirmatory study must be, from the pilot (methods critique, fix 7: power).

    py -3 eval/v2/power.py --set pilot [--delta 0.15] [--model haiku]

Takes each pilot family's calibration rate under prompt and medium (natural and format prompts)
and the facts stated per run, then simulates the primary test (sign-flip over families) for 16
families with 1 to 4 repeats, and for 24 and 32 families (which need more families written). It
prints the power to detect a ``delta`` difference (default 15 points) and the runs each design
costs, so the run count is set by power, not by budget alone.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import score
import stats

TASKS_PER_FAMILY = 2  # near and far
STYLES = 3  # natural, format, antihedge are all run, though only two enter the primary test
CONDITIONS = 5  # off, prompt, rules, placebo, medium


def family_rates(runs: list[dict]) -> list[tuple[float, float, int]]:
    by_family: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in runs:
        if r["variant"] in ("natural", "format"):
            by_family[r["family"]][r["condition"]].append(r)
    out = []
    for conds in by_family.values():
        if "prompt" not in conds or "medium" not in conds:
            continue
        a, b = score.rates(conds["prompt"])["calibrated"], score.rates(conds["medium"])["calibrated"]
        if a[1] and b[1]:
            facts = round((a[1] + b[1]) / (len(conds["prompt"]) + len(conds["medium"])))
            # Under the null both conditions share the pooled rate; the simulation adds delta to b.
            pooled = (a[0] + b[0]) / (a[1] + b[1])
            out.append((pooled, pooled, max(1, facts) * TASKS_PER_FAMILY * 2))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/v2/power.py")
    parser.add_argument("--set", dest="run_set", default="pilot")
    parser.add_argument("--model")
    parser.add_argument("--delta", type=float, default=0.15)
    args = parser.parse_args(argv)
    rates = family_rates(score.load(args.run_set, args.model))
    if not rates:
        print("no pilot families with both prompt and medium runs")
        return 1
    print(f"{len(rates)} pilot families; power to detect {args.delta:+.0%} (alpha 0.05):")
    print("| Families | Repeats | Power | Runs (all styles, 5 conditions) |")
    print("| --- | --- | --- | --- |")
    for families, repeats in [(16, 1), (16, 2), (16, 3), (16, 4), (24, 2), (24, 3), (32, 2)]:
        p = stats.power(rates, families, repeats, args.delta)
        runs = families * TASKS_PER_FAMILY * STYLES * CONDITIONS * repeats
        print(f"| {families} | {repeats} | {p:.0%} | {runs} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
