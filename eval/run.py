"""Eval runner: tasks × conditions × repeats via isolated `claude -p` runs; resumable and cost-capped.

    py -3 eval/run.py [--suite v1|v2] [--set dry|pilot|confirmatory] [--tasks a,b]
                      [--variants ...] [--conditions ...] [--repeats 2] [--model haiku]
                      [--daily-cap 2.0] [--max-runs N] [--max-turns 6] [--dry-run]

Conditions. **off** runs without the plugin; **low** records only (the sidecar builds the ledger and
report, nothing reaches Claude); **medium** records and refeeds; **high** adds the retry. Study v2
adds three controls (docs/findings/methods-critique.md, fix 1):

- **prompt**: no plugin, plus one system line asking Claude to keep sources' qualifiers. The
  cheapest thing that could produce Medium's effect.
- **rules**: Medium with the Administrator off (``backend = "none"``): rule-built rows refed, no
  sidecar calls.
- **placebo**: Medium with the refeed's qualifiers masked out (``refeed = "placebo"``): the same
  reminder of the fact, without the hedge.

Suites. **v1** is the frozen exploratory corpus (eval/tasks, tests/sandbox; variants natural and
pressure). **v2** is the redesigned study (eval/v2, built by eval/v2/build.py; variants natural,
format and antihedge). v2 runs go to eval/runs/<set>/v2/ so dry runs, the pilot and confirmatory
runs never mix; v1 runs stay in eval/runs/.

Each run lands in <runs>/<task>__<variant>__<condition>__r<n>__<model>/ with result.json (cost,
turns, tokens per step), the hook recording (events.jsonl), the store (store/) and the session
transcript (transcript.jsonl), from which distance in tokens and re-reads are measured. A run whose
result.json has returncode 0 is skipped, so an interrupted batch resumes where it stopped.

Invalid runs (protocol v2): a run that exits non-zero is retried on the next invocation; a run that
exits 0 with an empty final answer is retried once at once, and if it is still empty it is kept
with ``invalid: true`` and scored as stating nothing. Every run is appended to eval/ledger.jsonl,
and the batch stops once today's spend reaches --daily-cap, after --max-runs runs, or at the first
run that fails on a usage or rate limit. Never start a batch without deciding the day's budget.
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
V2 = REPO / "eval" / "v2"
sys.path.insert(0, str(REPO / "scripts"))

from live import LEDGER, TEST_ENV, spent_today

# Condition -> the plugin mode written to config.toml (None: no plugin).
CONDITIONS: dict[str, str | None] = {"off": None, "prompt": None, "low": "low", "rules": "medium",
                                     "placebo": "medium", "medium": "medium", "high": "high"}
EXTRA_CONFIG = {"rules": 'backend = "none"', "placebo": 'refeed = "placebo"'}
PROMPT_ONLY = "When you state a figure from a source, keep the source's qualifiers."
SYSTEM_PROMPTS = {"prompt": PROMPT_ONLY}
SUITES = {
    "v1": {"variants": {"natural": "prompt.txt", "pressure": "prompt-pressure.txt"},
           "conditions": "off,low,medium,high"},
    "v2": {"variants": {"natural": "prompt-natural.txt", "format": "prompt-format.txt",
                        "antihedge": "prompt-antihedge.txt"},
           "conditions": "off,prompt,rules,placebo,medium"},
    "probe": {"variants": {"natural": "prompt-natural.txt"}, "conditions": "off"},
}
SUITE_DIRS = {"v2": V2, "probe": V2 / "probe"}
VARIANTS = SUITES["v1"]["variants"]  # v1 names, kept for older callers
SETS = ("dry", "pilot", "confirmatory")
LIMITED = re.compile(r"usage limit|rate limit|limit reached|429|overloaded|quota|credit balance",
                     re.IGNORECASE)
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
              "output_tokens")


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


def sandbox_dir(task: str, suite: str = "v1") -> Path:
    if suite in SUITE_DIRS:
        return SUITE_DIRS[suite] / "sandbox" / task
    return REPO / "tests" / "sandbox" / task


def task_ids(suite: str) -> list[str]:
    if suite in SUITE_DIRS:
        return sorted(p.stem for p in (SUITE_DIRS[suite] / "tasks").glob("*.json"))
    return sorted(p.stem for p in TASKS.glob("*.toml"))


def steps_for(task: str, variant: str = "natural", suite: str = "v1") -> list[str]:
    name = SUITES[suite]["variants"][variant]
    text = (sandbox_dir(task, suite) / name).read_text(encoding="utf-8")
    return [s.strip() for s in text.split("\n---\n") if s.strip()]


def hit_limit(record: dict) -> bool:
    """A failed run that ran into plan usage or rate limits: stop the batch, resume later."""
    return record["returncode"] != 0 and bool(
        LIMITED.search(record.get("stderr", "") + " " + record.get("result", "")))


def _transcript(config_dir: str, session_id: str | None) -> Path | None:
    if not session_id:
        return None
    return next(iter(Path(config_dir).glob(f"projects/*/{session_id}.jsonl")), None)


def run_one(task: str, variant: str, condition: str, model: str, max_turns: int,
            out: Path, suite: str = "v1") -> dict:
    """One isolated run: sandbox copy with the condition's config, every step, recording kept."""
    # resolve(): Windows hands out 8.3 short temp paths (DRYDEN~1), which Claude Code does not
    # treat as inside its working folder, so acceptEdits would still deny writing notes.md.
    work = Path(tempfile.mkdtemp(prefix="qlaudified-eval-")).resolve()
    sandbox = work / task
    shutil.copytree(sandbox_dir(task, suite), sandbox,
                    ignore=shutil.ignore_patterns("prompt*.txt", ".claude"))
    store = sandbox / ".claude" / ".qlaudified"
    mode = CONDITIONS[condition]
    if mode is not None:
        store.mkdir(parents=True)
        lines = [f'mode = "{mode}"', EXTRA_CONFIG.get(condition, "")]
        (store / "config.toml").write_text("\n".join(filter(None, lines)) + "\n", encoding="utf-8")
    env = {**os.environ, **TEST_ENV, "QLAUDIFIED_RECORD_DIR": str(work / "record")}
    env.pop("CLAUDE_CODE_SKIP_PROMPT_HISTORY", None)  # --resume steps need the transcript
    env.pop("QLAUDIFIED_OFFLINE", None)
    turns_cap = max_turns + (1 if condition == "high" else 0)
    plugin = ["--plugin-dir", str(REPO)] if mode is not None else []
    system = (["--append-system-prompt", SYSTEM_PROMPTS[condition]]
              if condition in SYSTEM_PROMPTS else [])
    base = [*plugin, *system, "--model", model, "--max-turns", str(turns_cap),
            "--allowedTools", "Read,Grep,Glob,Bash" + (",Write,Edit" if suite != "v1" else ""),
            *(["--permission-mode", "acceptEdits"] if suite != "v1" else []),  # notes.md in the sandbox
            "--permission-prompts", "none",
            "--output-format", "json"]
    start = time.time()
    cost, turns, session_id, returncode, data, stderr = 0.0, 0, None, 0, {}, b""
    usage_steps: list[dict] = []
    for step in steps_for(task, variant, suite):
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
        usage = data.get("usage") or {}
        usage_steps.append({k: usage.get(k) or 0 for k in USAGE_KEYS})
        session_id = data.get("session_id") or session_id
        returncode, stderr = proc.returncode, proc.stderr
        if returncode != 0 or not session_id:
            break
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": task, "variant": variant,
        "condition": condition, "suite": suite,
        "model": model, "returncode": returncode, "wall_s": round(time.time() - start, 1),
        "total_cost_usd": round(cost, 6), "num_turns": turns, "session_id": session_id,
        "usage_steps": usage_steps,
        "usage": {k: sum(s[k] for s in usage_steps) for k in USAGE_KEYS},
        "result": data.get("result") or "", "stderr": stderr.decode("utf-8", "replace")[-1000:],
        "plugin_dir": str(REPO) if mode is not None else None,
        "system_prompt": SYSTEM_PROMPTS.get(condition),
    }
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if (work / "record" / "events.jsonl").exists():
        shutil.copy(work / "record" / "events.jsonl", out / "events.jsonl")
    if store.exists():
        shutil.copytree(store, out / "store", dirs_exist_ok=True)
    transcript = _transcript(env["CLAUDE_CONFIG_DIR"], session_id)
    if transcript:
        shutil.copy(transcript, out / "transcript.jsonl")
    (out / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return record


def runs_dir(suite: str, run_set: str | None) -> Path:
    if suite == "v1":
        return RUNS / run_set / "v1" if run_set else RUNS
    if run_set not in SETS:
        raise SystemExit(f"{suite} runs need --set dry, pilot or confirmatory")
    return RUNS / run_set / suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/run.py")
    parser.add_argument("--suite", default="v1", choices=sorted(SUITES))
    parser.add_argument("--set", dest="run_set", choices=SETS,
                        help="v2: which analysis the runs belong to (kept in separate folders)")
    parser.add_argument("--tasks", help="comma-separated task IDs (default: all)")
    parser.add_argument("--variants", help="default: every variant of the suite")
    parser.add_argument("--conditions", help="default: v1 off,low,medium,high; "
                                             "v2 off,prompt,rules,placebo,medium")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--daily-cap", type=float, default=2.0, help="USD estimate per day")
    parser.add_argument("--max-runs", type=int, help="stop after this many runs in this batch")
    parser.add_argument("--dry-run", action="store_true", help="list the runs, start nothing")
    args = parser.parse_args(argv)

    suite = SUITES[args.suite]
    runs = runs_dir(args.suite, args.run_set)
    tasks = args.tasks.split(",") if args.tasks else task_ids(args.suite)
    for task in tasks:  # fail early on typos
        if args.suite in SUITE_DIRS:
            json.loads((SUITE_DIRS[args.suite] / "tasks" / f"{task}.json").read_text(encoding="utf-8"))
        else:
            tomllib.loads((TASKS / f"{task}.toml").read_text(encoding="utf-8"))
    conditions = (args.conditions or suite["conditions"]).split(",")
    variants = (args.variants or ",".join(suite["variants"])).split(",")
    unknown = (set(conditions) - set(CONDITIONS)) | (set(variants) - set(suite["variants"]))
    if unknown:
        raise SystemExit(f"unknown conditions or variants: {', '.join(sorted(unknown))}")
    # Repeat-major: if a cap bites, every task has its first repeat in every variant and
    # condition. Conditions sit innermost, so a task's conditions run back to back.
    plan = [(t, v, c, r) for r in range(1, args.repeats + 1) for v in variants for t in tasks
            for c in conditions]
    todo = [p for p in plan if not done(runs / run_id(*p, args.model))]
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
        record = run_one(task, variant, condition, args.model, args.max_turns, runs / rid,
                         args.suite)
        if record["returncode"] == 0 and not record["result"].strip():
            record = run_one(task, variant, condition, args.model, args.max_turns, runs / rid,
                             args.suite)  # protocol v2: one immediate retry of an empty answer
            if record["returncode"] == 0 and not record["result"].strip():
                record["invalid"] = True
                (runs / rid / "result.json").write_text(json.dumps(record, indent=2),
                                                        encoding="utf-8")
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in record.items()
                                if k not in ("stderr", "usage_steps")}) + "\n")
        print(f"[{i}/{len(todo)}] {rid}: rc={record['returncode']} "
              f"${record['total_cost_usd']:.4f} {record['wall_s']}s", flush=True)
        if hit_limit(record):
            print("stopped: usage or rate limit; rerun later to resume")
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
