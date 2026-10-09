"""Score study v2 runs (protocol: docs/findings/protocol-v2.md).

    py -3 eval/v2/score.py --set pilot [--model haiku] [--out report.md] [--rows rows.csv]

Reads eval/runs/<set>/v2/*/, scores every fact of every run with calib.py (no plugin code is
imported), and reports per condition and prompt style: stated rate, calibration (the primary
outcome: stated facts expressed with the source's certainty), hedged facts kept, inflation,
over-hedging of firm facts, format compliance, re-reads, distance in tokens, tokens by component
and latency. Then the pre-registered contrasts, with families as the unit:

- **Primary:** calibration, medium vs prompt, natural and format prompts pooled.
- **Secondary (Holm-adjusted):** medium vs placebo, medium vs rules, prompt vs off, medium vs off,
  and over-hedging (firm facts deflated) medium vs off.
- **Antihedge prompts** are reported separately and descriptively: there the user asked for no
  hedging, so calibration and compliance pull in opposite directions.

``--rows`` writes one row per (run, fact) for the judge and the human labelling sheet.
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import calib
import stats
import transcript

CONDITIONS = ["off", "prompt", "low", "rules", "placebo", "medium", "high"]
STYLES = ["natural", "format", "antihedge"]
PRIMARY = ("prompt", "medium")
SECONDARY = [("placebo", "medium"), ("rules", "medium"), ("off", "prompt"), ("off", "medium")]
TOKEN_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
              "output_tokens")


def load_task(task: str) -> dict:
    path = HERE / "tasks" / f"{task}.json"
    if not path.exists():
        path = HERE / "probe" / "tasks" / f"{task}.json"  # difficulty-probe tasks
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(paths: list[Path]) -> list[dict]:
    out = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def score_run(folder: Path) -> dict | None:
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    if result.get("returncode") != 0:
        return None
    task = load_task(result["task"])
    answer = "" if result.get("invalid") else result.get("result") or ""
    facts = calib.score_answer(answer, task["facts"])
    sessions = list((folder / "store" / "sessions").glob("*")) if (folder / "store").exists() else []
    sidecar = _jsonl([s / "usage.jsonl" for s in sessions if (s / "usage.jsonl").exists()])
    timings = _jsonl([s / "timings.jsonl" for s in sessions if (s / "timings.jsonl").exists()])
    tr = folder / "transcript.jsonl"
    measured = transcript.measure(tr, task["read"]) if tr.exists() else {}
    return {
        "run": folder.name, "task": task["id"], "family": task["family"],
        "distance": task["distance"], "scope": task["scope"], "format": task["format"],
        "variant": result["variant"], "condition": result["condition"], "model": result["model"],
        "facts": facts, "complies": calib.complies(answer, task["format"], result["variant"]),
        "invalid": bool(result.get("invalid")),
        "distance_tokens": measured.get("distance_tokens"), "reread": measured.get("reread"),
        "agent_tokens": result.get("usage") or {},
        "sidecar_tokens": {"input": sum(u.get("input_tokens") or 0 for u in sidecar),
                           "output": sum(u.get("output_tokens") or 0 for u in sidecar),
                           "calls": len(sidecar)},
        "post_ms": [t["elapsed_ms"] for t in timings if t.get("event") == "PostToolUse"],
        "stop_ms": [t["elapsed_ms"] for t in timings if t.get("event") == "Stop"],
        "cost_usd": result.get("total_cost_usd") or 0.0,
    }


def load(run_set: str, model: str | None) -> list[dict]:
    root = REPO / "eval" / "runs" / run_set / "v2"
    runs = [score_run(f) for f in sorted(root.glob("*")) if (f / "result.json").exists()]
    return [r for r in runs if r and (model is None or r["model"] == model)]


# --- outcome rates ---------------------------------------------------------------------------

def _facts(runs: list[dict], hedged: bool | None = None) -> list[calib.FactScore]:
    return [f for r in runs for f in r["facts"] if hedged is None or f.hedged_source == hedged]


def rates(runs: list[dict]) -> dict:
    allf = _facts(runs)
    stated = [f for f in allf if f.stated]
    hedged = [f for f in stated if f.hedged_source]
    firm = [f for f in stated if not f.hedged_source]
    comp = [r["complies"] for r in runs if r["complies"] is not None]
    far = [r["distance_tokens"] for r in runs if r["distance"] == "far" and r["distance_tokens"]]
    rr = [r["reread"] for r in runs if r["reread"] is not None]
    return {
        "runs": len(runs),
        "stated": (len(stated), len(allf)),
        "calibrated": (sum(f.outcome == "kept" for f in stated), len(stated)),
        "hedged_kept": (sum(f.outcome == "kept" for f in hedged), len(hedged)),
        "inflated": (sum(f.outcome == "inflated" for f in hedged), len(hedged)),
        "deflated": (sum(f.outcome == "deflated" for f in firm), len(firm)),
        "complies": (sum(comp), len(comp)),
        "reread": (sum(rr), len(rr)),
        "far_tokens": sorted(far)[len(far) // 2] if far else None,
    }


def _pct(pair: tuple[int, int]) -> str:
    num, den = pair
    return f"{100 * num / den:.0f}% ({num}/{den})" if den else "–"


def _p95(values: list[float]) -> str:
    values = sorted(values)
    return f"{values[min(len(values) - 1, int(0.95 * len(values)))] / 1000:.1f} s" if values else "–"


def _tokens(runs: list[dict]) -> str:
    if not runs:
        return "–"
    agent = {k: sum(r["agent_tokens"].get(k) or 0 for r in runs) / len(runs) for k in TOKEN_KEYS}
    side_in = sum(r["sidecar_tokens"]["input"] for r in runs) / len(runs)
    side_out = sum(r["sidecar_tokens"]["output"] for r in runs) / len(runs)
    fresh = agent["input_tokens"] + agent["cache_creation_input_tokens"]
    text = f"{fresh / 1000:.1f}k / {agent['cache_read_input_tokens'] / 1000:.1f}k / " \
           f"{agent['output_tokens'] / 1000:.1f}k"
    if side_in or side_out:
        text += f" + sidecar {side_in / 1000:.1f}k / {side_out / 1000:.1f}k"
    return text


def table(runs: list[dict]) -> str:
    head = ("| Condition | Style | Runs | Stated | **Calibrated** | Hedged kept | Inflated | "
            "Over-hedged (firm) | Complies | Re-read | Far distance | Tokens per run (agent in / "
            "cached / out) | PostToolUse p95 | Stop p95 |")
    lines = [head, "| " + " | ".join(["---"] * 14) + " |"]
    for cond in CONDITIONS:
        for style in STYLES:
            sub = [r for r in runs if r["condition"] == cond and r["variant"] == style]
            if not sub:
                continue
            x = rates(sub)
            lines.append(
                f"| {cond} | {style} | {x['runs']} | {_pct(x['stated'])} | {_pct(x['calibrated'])} "
                f"| {_pct(x['hedged_kept'])} | {_pct(x['inflated'])} | {_pct(x['deflated'])} "
                f"| {_pct(x['complies'])} | {_pct(x['reread'])} | "
                f"{x['far_tokens'] if x['far_tokens'] is not None else '–'} | {_tokens(sub)} | "
                f"{_p95([m for r in sub for m in r['post_ms']])} | "
                f"{_p95([m for r in sub for m in r['stop_ms']])} |")
    return "\n".join(lines) + "\n"


def distance_table(runs: list[dict]) -> str:
    lines = ["| Condition | Hedged kept, near | Hedged kept, far |", "| --- | --- | --- |"]
    for cond in CONDITIONS:
        sub = [r for r in runs if r["condition"] == cond and r["variant"] != "antihedge"]
        if not sub:
            continue
        cells = [_pct(rates([r for r in sub if r["distance"] == d])["hedged_kept"])
                 for d in ("near", "far")]
        lines.append(f"| {cond} | {cells[0]} | {cells[1]} |")
    return "\n".join(lines) + "\n"


# --- contrasts --------------------------------------------------------------------------------

def family_diffs(runs: list[dict], a: str, b: str, outcome: str) -> list[float]:
    """Per-family difference b minus a in the outcome's rate (pooled over tasks, styles, repeats)."""
    by_family: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in runs:
        by_family[r["family"]][r["condition"]].append(r)
    diffs = []
    for conds in by_family.values():
        if a not in conds or b not in conds:
            continue
        ra, rb = rates(conds[a])[outcome], rates(conds[b])[outcome]
        if ra[1] and rb[1]:
            diffs.append(rb[0] / rb[1] - ra[0] / ra[1])
    return diffs


def contrast_line(name: str, diffs: list[float], p: float | None = None) -> str:
    if not diffs:
        return f"- {name}: no families with both conditions"
    lo, hi = stats.bootstrap_ci(diffs)
    p = stats.sign_flip(diffs) if p is None else p
    return (f"- {name}: {100 * stats.mean(diffs):+.1f} points over {len(diffs)} families "
            f"(family bootstrap 95% [{100 * lo:+.1f}, {100 * hi:+.1f}]; sign-flip p = {p:.3g})")


def contrasts(runs: list[dict]) -> str:
    main = [r for r in runs if r["variant"] in ("natural", "format")]
    out = ["Primary (calibration, natural and format prompts):", ""]
    a, b = PRIMARY
    out.append(contrast_line(f"{b} vs {a}", family_diffs(main, a, b, "calibrated")))
    tests = {f"calibration, {b} vs {a}": family_diffs(main, a, b, "calibrated")
             for a, b in SECONDARY}
    tests["over-hedging of firm facts, medium vs off"] = family_diffs(main, "off", "medium",
                                                                     "deflated")
    raw = {k: stats.sign_flip(v) for k, v in tests.items() if v}
    adjusted = stats.holm(raw)
    out += ["", "Secondary (Holm-adjusted p):", ""]
    out += [contrast_line(k, tests[k], adjusted[k]) for k in tests if k in adjusted]
    anti = [r for r in runs if r["variant"] == "antihedge"]
    if anti:
        out += ["", "Antihedge prompts (descriptive; the user asked for no hedging):", ""]
        for a, b in [PRIMARY, ("off", "medium")]:
            d = family_diffs(anti, a, b, "calibrated")
            if d:
                out.append(f"- calibration, {b} vs {a}: {100 * stats.mean(d):+.1f} points over "
                           f"{len(d)} families")
            c = family_diffs(anti, a, b, "complies")
            if c:
                out.append(f"- compliance, {b} vs {a}: {100 * stats.mean(c):+.1f} points")
    return "\n".join(out) + "\n"


def report(runs: list[dict]) -> str:
    models = sorted({r["model"] for r in runs})
    invalid = sum(r["invalid"] for r in runs)
    note = f" ({invalid} invalid, scored as stating nothing)" if invalid else ""
    parts = [f"## Study v2 · {', '.join(models)} · {len(runs)} runs{note}", "",
             table(runs), "Hedged facts kept by distance (natural and format prompts):", "",
             distance_table(runs), contrasts(runs)]
    return "\n".join(parts)


def write_rows(runs: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run", "task", "family", "condition", "variant", "fact", "hedged_source",
                    "stated", "hedged_answer", "outcome", "scope"])
        for r in runs:
            for fs in r["facts"]:
                w.writerow([r["run"], r["task"], r["family"], r["condition"], r["variant"],
                            fs.fact, fs.hedged_source, fs.stated, fs.hedged_answer, fs.outcome,
                            fs.scope])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/v2/score.py")
    parser.add_argument("--set", dest="run_set", required=True,
                        choices=["dry", "pilot", "confirmatory"])
    parser.add_argument("--model")
    parser.add_argument("--out", help="also write the report to this markdown file")
    parser.add_argument("--rows", help="write per-fact rows to this CSV")
    args = parser.parse_args(argv)
    runs = load(args.run_set, args.model)
    if not runs:
        print("no finished runs found")
        return 1
    text = report(runs)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    if args.rows:
        write_rows(runs, Path(args.rows))
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
