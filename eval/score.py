"""Offline scoring of recorded runs against the tasks' ground truth (design.md, Metrics).

    py -3 eval/score.py [--runs eval/runs] [--model haiku] [--out results.md] [--nli]

Every run's final answer is re-verified offline with the same rules (tiers 1, plus NLI with
--nli), against the spans that run captured, so all conditions are judged alike:

- **off**: Low-mode runs as Claude answered them; nothing is shown to the user.
- **post-hoc**: the same off runs, with the offline verification as the user's report.
- **medium**, **high**: the plugin's own conditions (high's answer is the one after any retry).

Metrics per condition, per model and prompt variant, with 95% intervals from resampling tasks:
- Uncaught drops (the headline): qualifier drops that reach the user unflagged, per hedged fact
  stated. In off, every drop is uncaught; post-hoc, medium and high subtract the flagged ones.
- Qualifiers kept: hedged ground-truth facts the answer states with their strongest hedge class.
- Drops flagged: of the facts stated without their qualifier, how many the verifier labelled
  qualifier-dropped (n/a for off, which shows the user nothing).
- Verifier accuracy: verdicts on ground-truth fact claims and on invented figures, against the
  true label (supported, qualifier-dropped, unsupported).
- Attribution precision and recall: fact claims citing the ground-truth span.
- Cost per run (total_cost_usd plus usage.jsonl) and overhead against off, paired by task.
- PostToolUse and Stop p95 from timings.jsonl.

Then the pre-registered paired comparisons (docs/findings/sprint-5.md), b minus a by task.
"""

import argparse
import json
import os
import statistics
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from qlaudified import indexer, lexicon, text
from qlaudified.config import Config
from qlaudified.store import Span, Store, Turn
from qlaudified.verify import claims as claim_split
from qlaudified.verify import verify_answer

ORDER = ["off", "post-hoc", "medium", "high"]


def load_task(task: str) -> dict:
    return tomllib.loads((REPO / "eval" / "tasks" / f"{task}.toml").read_text(encoding="utf-8"))


def load_runs(runs: Path, model: str | None = None) -> list[dict]:
    out = []
    for folder in sorted(p for p in runs.iterdir() if (p / "result.json").exists()):
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        if record.get("returncode") != 0 or (model and record.get("model") != model):
            continue
        out.append({**record, "folder": folder})
    return out


def run_store(folder: Path) -> Store | None:
    sessions = sorted((folder / "store" / "sessions").glob("*/index.sqlite"))
    return Store(sessions[0].parent) if sessions else None


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def source_classes(task: dict, fact: dict) -> set[str]:
    lines = (REPO / task["sandbox"] / fact["source"]).read_text(encoding="utf-8").splitlines()
    return set(indexer.find_hedges(lines[int(fact["locator"].lstrip("L")) - 1]))


def score_run(run: dict, task: dict) -> dict:
    """Per-run counts; summed per condition by ``table``."""
    store = run_store(run["folder"])
    spans: list[Span] = store.spans() if store else []
    answer = run.get("result") or ""
    verified, _ = verify_answer(answer, spans, Turn(1, "score", answer, ""), Config(),
                                extra_qualifiers=store.sidecar_qualifiers() if store else None)
    by_text = {c.text: c for c in verified}
    pairs = claim_split.claims_in_context(answer)
    s: dict = defaultdict(int)
    for fact in task.get("facts", []):
        stated = [(c, sent) for c, sent in pairs
                  if any(text.number_match(fact["value"], n) for n in text.numbers(text.clean(c)))]
        if not stated:
            continue
        claim, sentence = stated[0]
        s["stated"] += 1
        classes = source_classes(task, fact)
        truth = "supported"
        if classes:
            s["hedged"] += 1
            if lexicon.strongest(classes) in indexer.find_hedges(text.clean(sentence)):
                s["kept"] += 1
            else:
                truth = "qualifier-dropped"
                s["dropped"] += 1
        verdict = by_text[claim].verdict if claim in by_text else "skipped"
        if truth == "qualifier-dropped" and verdict == "qualifier-dropped":
            s["flagged"] += 1
        s["judged"] += 1
        s["correct"] += verdict == truth
        want = {sp.span_id for sp in spans
                if sp.source == fact["source"] and sp.locator == fact["locator"]}
        cited = set(by_text[claim].span_ids) if claim in by_text else set()
        if cited:
            s["cited"] += 1
            s["cited_right"] += bool(cited & want)
    # Invented figures: numbers stated that no file in the sandbox contains.
    known = {n for sp in spans for n in text.split_numbers(sp.numbers)}
    for claim, _ in pairs:
        nums = text.numbers(text.clean(claim))
        if nums and not any(text.number_match(n, k) for n in nums for k in known):
            s["invented"] += 1
            s["judged"] += 1
            s["correct"] += by_text[claim].verdict == "unsupported" if claim in by_text else 0
    folder = run["folder"]
    s["cost"] = (run.get("total_cost_usd") or 0) + sum(
        u.get("cost_usd") or 0 for u in _jsonl(next(iter(folder.glob("store/sessions/*/usage.jsonl")),
                                                    Path("-"))))
    timings = _jsonl(next(iter(folder.glob("store/sessions/*/timings.jsonl")), Path("-")))
    s["post_ms"] = [t["elapsed_ms"] for t in timings if t["event"] == "PostToolUse"]
    s["stop_ms"] = [t["elapsed_ms"] for t in timings if t["event"] == "Stop"]
    return dict(s)


def scored_rows(runs: list[dict]) -> list[dict]:
    """One row per run and condition; each off run also appears as post-hoc. ``uncaught`` counts
    qualifier drops that reach the user unflagged: all of them in off, which shows nothing."""
    rows = []
    for run in runs:
        s = score_run(run, load_task(run["task"]))
        base = {"task": run["task"], "model": run.get("model", ""),
                "variant": run.get("variant", "natural"), **s}
        conditions = [run["condition"]] + (["post-hoc"] if run["condition"] == "off" else [])
        for condition in conditions:
            flagged = 0 if condition == "off" else s.get("flagged", 0)
            rows.append({**base, "condition": condition,
                         "uncaught": s.get("dropped", 0) - flagged})
    return rows


def rate(num: str, den: str):
    def metric(rows: list[dict]) -> float | None:
        d = sum(r.get(den, 0) for r in rows)
        return sum(r.get(num, 0) for r in rows) / d if d else None
    return metric


METRICS = {
    "uncaught drops": rate("uncaught", "hedged"),  # lower is better: the headline
    "qualifiers kept": rate("kept", "hedged"),
}


def bootstrap(rows_by_task: dict[str, list[dict]], metric, iterations: int = 2000,
              seed: int = 7) -> tuple[float, float] | None:
    """95% interval, resampling tasks (runs of one task are not independent)."""
    import random

    tasks = sorted(rows_by_task)
    if not tasks:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(iterations):
        sample = [r for t in rng.choices(tasks, k=len(tasks)) for r in rows_by_task[t]]
        value = metric(sample)
        if value is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    return values[int(0.025 * len(values))], values[min(len(values) - 1, int(0.975 * len(values)))]


def compare(rows: list[dict], a: str, b: str, metric, iterations: int = 2000,
            seed: int = 7) -> dict | None:
    """b minus a on a metric, paired by task: only tasks run under both conditions count."""
    import random

    by: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[r["task"]][r["condition"]].append(r)
    tasks = sorted(t for t, c in by.items() if c.get(a) and c.get(b))
    if not tasks:
        return None

    def diff(sample: list[str]) -> float | None:
        va = metric([r for t in sample for r in by[t][a]])
        vb = metric([r for t in sample for r in by[t][b]])
        return None if va is None or vb is None else vb - va

    point = diff(tasks)
    if point is None:
        return None
    rng = random.Random(seed)
    values = sorted(v for v in (diff(rng.choices(tasks, k=len(tasks)))
                                for _ in range(iterations)) if v is not None)
    return {"a": a, "b": b, "diff": point, "tasks": len(tasks),
            "ci": (values[int(0.025 * len(values))],
                   values[min(len(values) - 1, int(0.975 * len(values)))])}


def _p95(values: list[float]) -> str:
    if not values:
        return "–"
    values = sorted(values)
    return f"{values[min(len(values) - 1, int(0.95 * len(values)))]:.0f} ms"


def _pct(num: int, den: int) -> str:
    return f"{100 * num / den:.0f}% ({num}/{den})" if den else "–"


def _ci(rows: list[dict], metric) -> str:
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_task[r["task"]].append(r)
    ci = bootstrap(by_task, metric)
    return f" [{100 * ci[0]:.0f}–{100 * ci[1]:.0f}%]" if ci else ""


def table(runs: list[dict], rows: list[dict] | None = None) -> str:
    """The results table for one group of runs (one model and variant)."""
    rows = rows if rows is not None else scored_rows(runs)
    by_condition: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_condition[r["condition"]].append(r)
    off_cost: dict[str, list[float]] = defaultdict(list)
    for r in by_condition.get("off", []):
        off_cost[r["task"]].append(r["cost"])
    head = ("| Condition | Runs | Uncaught drops | Qualifiers kept | Drops flagged | "
            "Verifier accuracy | Attribution P / R | Cost per run | Overhead vs off | "
            "PostToolUse p95 | Stop p95 |")
    out = [head, "|" + " --- |" * 11]
    for condition in ORDER:
        scored = by_condition.get(condition)
        if not scored:
            continue

        def total(key: str, items=scored) -> int:
            return sum(r.get(key, 0) for r in items)

        overheads = []
        by_task: dict[str, list[float]] = defaultdict(list)
        for r in scored:
            by_task[r["task"]].append(r["cost"])
        for task, costs in by_task.items():
            if off_cost.get(task):
                base = statistics.mean(off_cost[task])
                overheads.append(statistics.mean(costs) / base - 1 if base else 0.0)
        overhead = "0% (offline)" if condition == "post-hoc" else (
            f"{100 * statistics.mean(overheads):+.1f}%" if overheads else "–")
        shows_user = condition != "off"
        out.append(" | ".join([
            f"| {condition}", str(len(scored)),
            _pct(total("uncaught"), total("hedged")) + _ci(scored, METRICS["uncaught drops"]),
            _pct(total("kept"), total("hedged")) + _ci(scored, METRICS["qualifiers kept"]),
            _pct(total("flagged"), total("dropped")) if shows_user else "n/a",
            _pct(total("correct"), total("judged")) if shows_user else "n/a",
            (f"{_pct(total('cited_right'), total('cited'))} / "
             f"{_pct(total('cited_right'), total('stated'))}") if shows_user else "n/a",
            f"${statistics.mean(r['cost'] for r in scored):.4f}", overhead,
            _p95([v for r in scored for v in r.get("post_ms", [])]),
            _p95([v for r in scored for v in r.get("stop_ms", [])]),
        ]) + " |")
    return "\n".join(out) + "\n"


# The pre-registered comparisons (docs/findings/sprint-5.md), b minus a.
COMPARISONS = [
    ("uncaught drops", "post-hoc", "medium"),  # H1, the headline
    ("qualifiers kept", "off", "medium"),  # H2
    ("qualifiers kept", "medium", "high"),  # H3
    ("uncaught drops", "medium", "high"),
]


def report(runs: list[dict]) -> str:
    rows = scored_rows(runs)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["variant"])].append(r)
    out = []
    for (model, variant), group in sorted(groups.items()):
        out += [f"## {model} · {variant} prompts", "", table([], group),
                "Paired by task (b − a, 95% bootstrap interval over tasks):", ""]
        for name, a, b in COMPARISONS:
            result = compare(group, a, b, METRICS[name])
            if result:
                lo, hi = result["ci"]
                out.append(f"- {name}, {b} vs {a}: {100 * result['diff']:+.0f} points "
                           f"[{100 * lo:+.0f}, {100 * hi:+.0f}] over {result['tasks']} tasks")
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/score.py")
    parser.add_argument("--runs", default=str(REPO / "eval" / "runs"))
    parser.add_argument("--model", help="only runs made with this model")
    parser.add_argument("--out", help="also write the report to this markdown file")
    parser.add_argument("--nli", action="store_true", help="let the NLI tier run, if installed")
    args = parser.parse_args(argv)
    if not args.nli:
        os.environ["QLAUDIFIED_CACHE"] = str(REPO / "eval" / "runs" / ".no-nli")
    runs = load_runs(Path(args.runs), args.model)
    if not runs:
        print("no finished runs found")
        return 1
    result = report(runs)
    print(result, end="")
    if args.out:
        Path(args.out).write_text(result, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
