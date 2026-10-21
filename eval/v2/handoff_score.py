"""Score handoff runs: does the answer made from an intermediate document keep the sources' hedges?

    py -3 eval/v2/handoff_score.py --set dry

One session per run. The answer is scored per focus intervention as in gauntlet_score.py (kept /
inflated / omitted for hedged, plain / deflated / omitted for firm), and the transcript shows what
the session opened: an abstract (the sources), data/findings.json (where some runs kept a
``caveats`` note) or neither. Read cells by hand before trusting a number: the lexicon counts
commentary, and a leaflet-style answer that states no effect at all is not a lost hedge.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import gauntlet_score

TASKS = HERE / "handoff" / "tasks"
RUNS = REPO / "eval" / "runs"


def opened(transcript: Path) -> dict[str, bool]:
    """Whether the session read an abstract, and whether it read data/findings.json."""
    seen = {"abstracts": False, "findings": False}
    if not transcript.exists():
        return seen
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            content = (json.loads(line).get("message") or {}).get("content") or []
        except (ValueError, AttributeError):
            continue
        for use in content if isinstance(content, list) else []:
            if not isinstance(use, dict) or use.get("type") != "tool_use":
                continue
            if gauntlet_score._abstract_access(use) == "read":
                seen["abstracts"] = True
            given = json.dumps(use.get("input") or {}).replace("\\\\", "/")
            if "findings.json" in given and use.get("name") not in gauntlet_score.hops_score.WRITES:
                seen["findings"] = True
    return seen


def score_run(folder: Path, task: dict) -> dict:
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    cells = gauntlet_score.score_text(result.get("result") or "", task, "focus", prose=True)
    return {"task": result["task"], "variant": result.get("variant", "?"),
            "cost": result.get("total_cost_usd", 0.0), "turns": result.get("num_turns", 0),
            "cells": cells, **opened(folder / "transcript.jsonl")}


def _rate(num: int, den: int) -> str:
    return f"{100 * num / den:.0f}% ({num}/{den})" if den else "n/a"


def report(runs: list[dict]) -> str:
    out = [("| Variant | Runs | Hedged kept (of stated) | Firm deflated (of stated) | Omitted "
            "| Read an abstract | Read findings.json |"),
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for variant in sorted({r["variant"] for r in runs}):
        group = [r for r in runs if r["variant"] == variant]
        cells = [c for r in group for c in r["cells"]]
        kept, infl, defl, plain, om = (sum(o == k for _, o in cells) for k in
                                       ("kept", "inflated", "deflated", "plain", "omitted"))
        out.append(f"| {variant} | {len(group)} | {_rate(kept, kept + infl)} | "
                   f"{_rate(defl, defl + plain)} | {_rate(om, len(cells))} | "
                   f"{sum(r['abstracts'] for r in group)}/{len(group)} | "
                   f"{sum(r['findings'] for r in group)}/{len(group)} |")
    out += ["", "| Run | Cost | Turns |", "| --- | --- | --- |"]
    out += [f"| {r['task']} {r['variant']} | ${r['cost']:.4f} | {r['turns']} |" for r in runs]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/v2/handoff_score.py")
    parser.add_argument("--set", dest="run_set", default="dry")
    args = parser.parse_args(argv)
    runs = []
    for folder in sorted((RUNS / args.run_set / "handoff").glob("*")):
        result = folder / "result.json"
        if not result.exists() or json.loads(result.read_text(encoding="utf-8")).get("returncode"):
            continue
        task = json.loads((TASKS / f"{folder.name.split('__')[0]}.json").read_text(encoding="utf-8"))
        runs.append(score_run(folder, task))
    if not runs:
        print(f"no finished runs in {RUNS / args.run_set / 'handoff'}")
        return 1
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(report(runs), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
