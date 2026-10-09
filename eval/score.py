"""Offline scoring of recorded runs against the tasks' ground truth (design revision 2).

    py -3 eval/score.py [--runs eval/runs] [--model haiku] [--out results.md] [--nli]

Conditions: **off** (no plugin), **low** (record only), **medium** (record + refeed), **high**
(+ one retry). Every final answer is re-checked offline with the same rules (tier 1; NLI with
--nli) so conditions are judged alike; the ledger each run built is scored against the ground
truth too.

Measures per condition, per model and prompt variant, with 95% intervals from resampling tasks:
- Qualifiers kept: hedged ground-truth facts the final answer states with the source's strongest
  hedge class.
- Kept at first use: the same, at the fact's first use in the loop (from the ledger).
- Uncaught drops: final-answer drops the report didn't flag, per hedged fact stated (all of them
  in off, which reports nothing).
- Ledger: planted facts recorded as rows; with the right source qualifiers; with the right origin
  (Provided Document when the prompt names the file, else Internal Document).
- Verifier accuracy: verdicts on fact claims and on invented figures against the true label.
- Consults: runs where Claude read provenance.csv.
- Cost per run (total_cost_usd plus the sidecar's usage.jsonl), overhead vs off paired by task,
  and the sidecar's cost per ledger row.
- PostToolUse and Stop p95 from timings.jsonl.

Then a decay table (qualifiers kept by distance) and the pre-registered comparisons
(docs/findings/sprint-5.md), b minus a, paired by task.
"""

import argparse
import json
import os
import statistics
import sys
import tomllib
from collections import defaultdict
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from qlaudified import indexer, lexicon, text
from qlaudified.config import Config
from qlaudified.store import Span, Store, Turn
from qlaudified.testing.spans import spans_from_files
from qlaudified.verify import claims as claim_split
from qlaudified.verify import verify_answer

ORDER = ["off", "low", "medium", "high"]
VARIANT_PROMPTS = {"natural": "prompt.txt", "pressure": "prompt-pressure.txt"}


@cache
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


def _jsonl(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _session_file(folder: Path, name: str) -> Path | None:
    return next(iter(folder.glob(f"store/sessions/*/{name}")), None)


def source_classes(task: dict, fact: dict) -> set[str]:
    lines = (REPO / task["sandbox"] / fact["source"]).read_text(encoding="utf-8").splitlines()
    return set(indexer.find_hedges(lines[int(fact["locator"].lstrip("L")) - 1]))


@cache
def sandbox_numbers(sandbox: str) -> frozenset[str]:
    """Every figure the task's files contain: a stated figure outside this set is invented."""
    folder = REPO / sandbox
    files = sorted(str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*.md"))
    return frozenset(n for s in spans_from_files(folder, *files) for n in text.split_numbers(s.numbers))


def expected_origin(task: dict, fact: dict, variant: str) -> str:
    if fact.get("origin"):
        return fact["origin"]
    prompt = (REPO / task["sandbox"] / VARIANT_PROMPTS.get(variant, "prompt.txt")).read_text(
        encoding="utf-8")
    return "Provided Document" if Path(fact["source"]).name in prompt else "Internal Document"


def _kept(classes: set[str], hedges_text: str | None) -> bool:
    return hedges_text is not None and lexicon.strongest(classes) in indexer.find_hedges(hedges_text)


def score_run(run: dict, task: dict) -> dict:
    """Per-run counts; summed per condition by ``table``."""
    store = run_store(run["folder"])
    facts: list[Span] = store.spans() if store else []
    answer = run.get("result") or ""
    verified, _ = verify_answer(answer, facts, Turn(1, "score", answer, ""), Config(),
                                extra_qualifiers=store.sidecar_qualifiers() if store else None)
    by_text = {c.text: c for c in verified}
    pairs = claim_split.claims_in_context(answer)
    variant = run.get("variant", "natural")
    s: dict = defaultdict(int)
    for fact in task.get("facts", []):
        classes = source_classes(task, fact)
        row = next((f for f in facts if f.source == fact["source"]
                    and f.locator == fact["locator"] and f.origin != "claude"), None)
        if store is not None:
            s["planted"] += 1
            if row is not None:
                s["recorded"] += 1
                s["quals_right"] += set(fact["qualifiers"]) <= set(row.qualifiers.split("; "))
                s["origin_right"] += row.category == expected_origin(task, fact, variant)
                if classes and row.first_use_step is not None:
                    s["first_used"] += 1
                    s["first_kept"] += _kept(classes, row.first_use_qualifiers.replace(";", " ")
                                             if row.first_use_qualifiers else "")
        stated = [(c, sent) for c, sent in pairs
                  if any(text.number_match(fact["value"], n) for n in text.numbers(text.clean(c)))]
        if not stated:
            continue
        claim, sentence = stated[0]
        s["stated"] += 1
        truth = "supported"
        if classes:
            s["hedged"] += 1
            if _kept(classes, text.clean(sentence)):
                s["kept"] += 1
            else:
                truth = "qualifier-dropped"
                s["dropped"] += 1
        verdict = by_text[claim].verdict if claim in by_text else "skipped"
        s["flagged"] += truth == "qualifier-dropped" and verdict == "qualifier-dropped"
        s["judged"] += 1
        s["correct"] += verdict == truth
    known = sandbox_numbers(task["sandbox"])
    for claim, _ in pairs:
        nums = text.numbers(text.clean(claim))
        if nums and not any(text.number_match(n, k) for n in nums for k in known):
            s["invented"] += 1
            s["judged"] += 1
            s["correct"] += by_text[claim].verdict == "unsupported" if claim in by_text else 0
    folder = run["folder"]
    sidecar = sum(u.get("cost_usd") or 0 for u in _jsonl(_session_file(folder, "usage.jsonl")))
    s["cost"] = (run.get("total_cost_usd") or 0) + sidecar
    s["sidecar_cost"] = sidecar
    s["rows"] = len(facts)
    consults = _jsonl(_session_file(folder, "consults.jsonl"))
    s["consulted"] = int(bool(consults))
    timings = _jsonl(_session_file(folder, "timings.jsonl"))
    s["post_ms"] = [t["elapsed_ms"] for t in timings if t["event"] == "PostToolUse"]
    s["stop_ms"] = [t["elapsed_ms"] for t in timings if t["event"] == "Stop"]
    return dict(s)


def scored_rows(runs: list[dict]) -> list[dict]:
    """One row per run. ``uncaught``: drops the user wasn't told about (all of them in off)."""
    rows = []
    for run in runs:
        task = load_task(run["task"])
        s = score_run(run, task)
        flagged = 0 if run["condition"] == "off" else s.get("flagged", 0)
        rows.append({"task": run["task"], "model": run.get("model", ""),
                     "variant": run.get("variant", "natural"), "condition": run["condition"],
                     "type": task.get("type", ""), "distance": task.get("distance"),
                     "compacted": task.get("compacted", False),
                     **s, "uncaught": s.get("dropped", 0) - flagged})
    return rows


def rate(num: str, den: str):
    def metric(rows: list[dict]) -> float | None:
        d = sum(r.get(den, 0) for r in rows)
        return sum(r.get(num, 0) for r in rows) / d if d else None
    return metric


METRICS = {
    "qualifiers kept": rate("kept", "hedged"),
    "kept at first use": rate("first_kept", "first_used"),
    "uncaught drops": rate("uncaught", "hedged"),
    "ledger facts": rate("recorded", "planted"),
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
    head = ("| Condition | Runs | Qualifiers kept | Kept at first use | Uncaught drops | "
            "Ledger: facts / qualifiers / origin | Verifier accuracy | Consults | Cost per run | "
            "Overhead vs off | Sidecar $/row | PostToolUse p95 | Stop p95 |")
    out = [head, "|" + " --- |" * 13]
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
        overhead = f"{100 * statistics.mean(overheads):+.1f}%" if overheads else "–"
        recorded = condition != "off"
        rows_total = total("rows")
        out.append(" | ".join([
            f"| {condition}", str(len(scored)),
            _pct(total("kept"), total("hedged")) + _ci(scored, METRICS["qualifiers kept"]),
            _pct(total("first_kept"), total("first_used")) if recorded else "n/a",
            _pct(total("uncaught"), total("hedged")) + _ci(scored, METRICS["uncaught drops"]),
            (f"{_pct(total('recorded'), total('planted'))} / "
             f"{_pct(total('quals_right'), total('recorded'))} / "
             f"{_pct(total('origin_right'), total('recorded'))}") if recorded else "n/a",
            _pct(total("correct"), total("judged")) if recorded else "n/a",
            _pct(total("consulted"), len(scored)) if condition in ("medium", "high") else "n/a",
            f"${statistics.mean(r['cost'] for r in scored):.4f}", overhead,
            f"${sum(r.get('sidecar_cost', 0) for r in scored) / rows_total:.5f}"
            if recorded and rows_total else "–",
            _p95([v for r in scored for v in r.get("post_ms", [])]),
            _p95([v for r in scored for v in r.get("stop_ms", [])]),
        ]) + " |")
    return "\n".join(out) + "\n"


def decay_table(rows: list[dict]) -> str:
    """Qualifiers kept in the final answer by distance from the read to the question."""
    decay = [r for r in rows if r["type"] == "decay"]
    if not decay:
        return ""
    columns = [("0 steps", 0, False), ("~5 steps", 5, False), ("~15 steps", 15, False),
               ("~15 + /compact", 15, True)]
    out = ["| Condition | " + " | ".join(c for c, _, _ in columns) + " |",
           "|" + " --- |" * (len(columns) + 1)]
    for condition in ORDER:
        cells = []
        for _, distance, compacted in columns:
            group = [r for r in decay if r["condition"] == condition and r["distance"] == distance
                     and bool(r["compacted"]) == compacted]
            cells.append(_pct(sum(r.get("kept", 0) for r in group),
                              sum(r.get("hedged", 0) for r in group)))
        if any(c != "–" for c in cells):
            out.append(f"| {condition} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


# The pre-registered comparisons (docs/findings/sprint-5.md), b minus a; the last element limits
# a comparison to the decay tasks at ~5 and ~15 steps (H1).
COMPARISONS = [
    ("qualifiers kept", "low", "medium", "decay"),  # H1, the headline
    ("qualifiers kept", "low", "medium", None),
    ("qualifiers kept", "off", "low", None),  # H3: within ±10 points
    ("qualifiers kept", "medium", "high", None),  # H4
    ("uncaught drops", "low", "medium", None),
]


def report(runs: list[dict]) -> str:
    rows = scored_rows(runs)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["variant"])].append(r)
    out = []
    for (model, variant), group in sorted(groups.items()):
        out += [f"## {model} · {variant} prompts", "", table([], group)]
        decay = decay_table(group)
        if decay:
            out += ["Qualifiers kept by distance (decay tasks):", "", decay]
        out += ["Paired by task (b − a, 95% bootstrap interval over tasks):", ""]
        for name, a, b, subset in COMPARISONS:
            pool = [r for r in group if subset is None or (
                r["type"] == "decay" and (r["distance"] or 0) >= 5)]
            result = compare(pool, a, b, METRICS[name])
            if result:
                lo, hi = result["ci"]
                where = " on decay tasks at ~5 and ~15 steps" if subset else ""
                out.append(f"- {name}, {b} vs {a}{where}: {100 * result['diff']:+.0f} points "
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
    if args.out:
        Path(args.out).write_text(result, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")  # a Windows console is cp1252; the report has "−"
    print(result, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
