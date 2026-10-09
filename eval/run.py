"""Eval runner: tasks × conditions × repeats via isolated `claude -p` runs; resumable and cost-capped.

    py -3 eval/run.py [--tasks a,b] [--variants natural,pressure] [--conditions off,medium,high]
                      [--repeats 2] [--model haiku] [--daily-cap 2.0] [--max-runs N]
                      [--max-turns 6] [--dry-run]

Conditions (design.md, Evaluation plan; Sprint 4 decision): **off** runs the plugin in Low mode,
so nothing reaches Claude's context but the spans are captured for the post-hoc condition, which
eval/score.py builds offline; **medium** and **high** set that mode. The mode is written to the
sandbox's config.toml before the run. High gets one extra turn for the Stop retry (VER-4).

Variants (Sprint 5): **natural** uses the task's prompt.txt; **pressure** uses
prompt-pressure.txt, the same question under a realistic constraint (a slide line, a table, a
headline, an executive summary) where models tend to drop qualifiers.

Each run lands in eval/runs/<task>__<variant>__<condition>__r<n>__<model>/ with result.json, the hook
recording (events.jsonl) and the store (store/). A run whose result.json has returncode 0 is
skipped, so an interrupted batch resumes where it stopped. Every run is appended to
eval/ledger.jsonl, and the batch stops once today's spend reaches --daily-cap, after --max-runs
runs, or at the first run that fails on a usage or rate limit (rerun later to resume). Never start a
batch without deciding the day's budget (eval/README.md).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TASKS = REPO / "eval" / "tasks"
RUNS = REPO / "eval" / "runs"
sys.path.insert(0, str(REPO / "scripts"))

from live import LEDGER, TEST_ENV, spent_today

CONDITIONS = {"off": "low", "medium": "medium", "high": "high"}
VARIANTS = {"natural": "prompt.txt", "pressure": "prompt-pressure.txt"}
LIMITED = re.compile(r"usage limit|rate limit|limit reached|429|overloaded|quota|credit balance",
                     re.IGNORECASE)


def run_id(task: str, variant: str, condition: str, repeat: int, model: str) -> str:
    return f"{task}__{variant}__{condition}__r{repeat}__{model}"


def done(folder: Path) -> bool:
    result = folder / "result.json"
    if not result.exists():
        return False
    try:
        return json.loads(result.read_text(encoding="utf-8")).get("returncode") == 0
    except ValueError:
        return False


def steps_for(task: str, variant: str = "natural") -> list[str]:
    text = (REPO / "tests" / "sandbox" / task / VARIANTS[variant]).read_text(encoding="utf-8")
    return [s.strip() for s in text.split("\n---\n") if s.strip()]


def hit_limit(record: dict) -> bool:
    """A failed run that ran into plan usage or rate limits: stop the batch, resume later."""
    return record["returncode"] != 0 and bool(
        LIMITED.search(record.get("stderr", "") + " " + record.get("result", "")))


def run_one(task: str, variant: str, condition: str, model: str, max_turns: int,
            out: Path) -> dict:
    """One isolated run: sandbox copy with the condition's mode, every step, recording kept."""
    work = Path(tempfile.mkdtemp(prefix="qlaudified-eval-"))
    sandbox = work / task
    shutil.copytree(REPO / "tests" / "sandbox" / task, sandbox,
                    ignore=shutil.ignore_patterns("prompt*.txt", ".claude"))
    store = sandbox / ".claude" / ".qlaudified"
    store.mkdir(parents=True)
    (store / "config.toml").write_text(f'mode = "{CONDITIONS[condition]}"\n', encoding="utf-8")
    env = {**os.environ, **TEST_ENV, "QLAUDIFIED_RECORD_DIR": str(work / "record")}
    env.pop("CLAUDE_CODE_SKIP_PROMPT_HISTORY", None)  # --resume steps need the transcript
    env.pop("QLAUDIFIED_OFFLINE", None)
    turns_cap = max_turns + (1 if condition == "high" else 0)
    base = ["--plugin-dir", str(REPO), "--model", model, "--max-turns", str(turns_cap),
            "--allowedTools", "Read,Grep,Glob,Bash", "--permission-prompts", "none",
            "--output-format", "json"]
    start = time.time()
    cost, turns, session_id, returncode, data, stderr = 0.0, 0, None, 0, {}, b""
    for step in steps_for(task, variant):
        resume = ["--resume", session_id] if session_id else []
        proc = subprocess.run(["claude", "-p", step, *resume, *base], cwd=sandbox, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, check=False,
                              shell=(os.name == "nt"))
        try:
            data = json.loads(proc.stdout.decode("utf-8", "replace"))
        except ValueError:
            data = {}
        cost += data.get("total_cost_usd") or 0.0
        turns += data.get("num_turns") or 0
        session_id = data.get("session_id") or session_id
        returncode, stderr = proc.returncode, proc.stderr
        if returncode != 0 or not session_id:
            break
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": task, "variant": variant,
        "condition": condition,
        "model": model, "returncode": returncode, "wall_s": round(time.time() - start, 1),
        "total_cost_usd": round(cost, 6), "num_turns": turns, "session_id": session_id,
        "result": data.get("result") or "", "stderr": stderr.decode("utf-8", "replace")[-1000:],
        "plugin_dir": str(REPO),
    }
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if (work / "record" / "events.jsonl").exists():
        shutil.copy(work / "record" / "events.jsonl", out / "events.jsonl")
    shutil.copytree(store, out / "store", dirs_exist_ok=True)
    (out / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/run.py")
    parser.add_argument("--tasks", help="comma-separated task IDs (default: all)")
    parser.add_argument("--variants", default="natural,pressure")
    parser.add_argument("--conditions", default="off,medium,high")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--daily-cap", type=float, default=2.0, help="USD estimate per day")
    parser.add_argument("--max-runs", type=int, help="stop after this many runs in this batch")
    parser.add_argument("--dry-run", action="store_true", help="list the runs, start nothing")
    args = parser.parse_args(argv)

    tasks = args.tasks.split(",") if args.tasks else sorted(p.stem for p in TASKS.glob("*.toml"))
    for task in tasks:
        tomllib.loads((TASKS / f"{task}.toml").read_text(encoding="utf-8"))  # fail early on typos
    conditions = args.conditions.split(",")
    variants = args.variants.split(",")
    unknown = (set(conditions) - set(CONDITIONS)) | (set(variants) - set(VARIANTS))
    if unknown:
        raise SystemExit(f"unknown conditions or variants: {', '.join(sorted(unknown))}")
    # Repeat-major: if a cap bites, every task has its first repeat in every variant and
    # condition. Conditions sit innermost, so a task's off/medium/high runs are back to back.
    plan = [(t, v, c, r) for r in range(1, args.repeats + 1) for v in variants for t in tasks
            for c in conditions]
    todo = [p for p in plan if not done(RUNS / run_id(*p, args.model))]
    print(f"{len(plan)} runs planned, {len(plan) - len(todo)} already done, {len(todo)} to run")
    if args.dry_run:
        for p in todo:
            print("  " + run_id(*p, args.model))
        return 0
    for i, (task, variant, condition, repeat) in enumerate(todo, 1):
        spent = spent_today()
        if spent >= args.daily_cap:
            print(f"daily cap reached: ${spent:.2f} of ${args.daily_cap:.2f}; rerun to resume")
            return 2
        if args.max_runs is not None and i > args.max_runs:
            print(f"--max-runs {args.max_runs} reached; rerun to resume")
            return 0
        rid = run_id(task, variant, condition, repeat, args.model)
        record = run_one(task, variant, condition, args.model, args.max_turns, RUNS / rid)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in record.items() if k != "stderr"}) + "\n")
        print(f"[{i}/{len(todo)}] {rid}: rc={record['returncode']} "
              f"${record['total_cost_usd']:.4f} {record['wall_s']}s", flush=True)
        if hit_limit(record):
            print("stopped: usage or rate limit; rerun later to resume")
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
