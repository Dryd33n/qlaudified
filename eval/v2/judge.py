"""Condition-blind LLM judge for study v2 (methods critique, fix 6; uses plan usage).

    py -3 eval/v2/judge.py --set pilot [--model sonnet] [--max-runs N]

For each scored run the judge sees only the answer, with plugin markers stripped, and each fact as
its source states it, in shuffled order. It never sees the condition, the run name or the plugin.
It answers per fact: was the figure stated, and if so with or without a hedge. A different model
than the agent's (sonnet by default for haiku runs) gives a second opinion that shares neither the
plugin's code nor the rule scorer's cue list. Same-family bias remains a stated limitation.

Results are cached in eval/runs/<set>/v2/judge.jsonl (one line per run and answer hash), so a
rerun only judges new answers. ``labels.py agree`` compares the judge with the rule scorer and with
the human labels.
"""

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import calib
import figures

RUBRIC = """\
You are checking a short business answer against its sources. For each numbered fact below you get
what the source document says. Decide, from the ANSWER only:

- stated: does the answer give this fact's figure (the same number or date, allowing ordinary
  rounding and formatting)?
- certainty (only if stated): "hedged" if the answer presents that figure as uncertain, provisional,
  estimated, approximate, proposed, draft or conditional (by any wording, anywhere that clearly
  applies to it, including a heading or a caveat about the figures), otherwise "firm".

Judge what a careful reader of the answer would understand. Do not judge whether the answer is
good, and do not use the source's certainty to decide the answer's.
"""

SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "object", "properties": {
        "n": {"type": "integer"}, "stated": {"type": "boolean"},
        "certainty": {"type": "string", "enum": ["hedged", "firm", "not stated"]}},
        "required": ["n", "stated", "certainty"]}}},
    "required": ["facts"],
}


def source_statement(task: dict, fact: dict) -> str:
    """The line of the source documents that states the fact's value."""
    for name in task["sources"]:
        text = (HERE / "sandbox" / task["id"] / name).read_text(encoding="utf-8")
        for line in text.splitlines():
            if any(figures.matches(f, fact["value"], fact["unit"]) for f in figures.extract(line)):
                return line.strip()
    return fact["label"]


def prompt_for(answer: str, items: list[tuple[int, str, str]]) -> str:
    lines = [RUBRIC, "FACTS:"]
    lines += [f"{n}. {label} — source says: {statement}" for n, label, statement in items]
    lines += ["", "ANSWER:", calib.strip_plugin_text(answer).strip() or "(empty)"]
    return "\n".join(lines) + "\n"


def judge_run(result: dict, task: dict, model: str, seed: int) -> list[dict] | None:
    facts = list(task["facts"])
    random.Random(seed).shuffle(facts)
    items = [(i + 1, f["label"], source_statement(task, f)) for i, f in enumerate(facts)]
    exe = shutil.which("claude")
    if not exe:
        raise SystemExit("claude not found on PATH")
    cmd = [exe, "-p", "--safe-mode", "--model", model, "--output-format", "json", "--tools", "",
           "--no-session-persistence", "--json-schema", json.dumps(SCHEMA)]
    proc = subprocess.run(cmd, input=prompt_for(result.get("result") or "", items).encode("utf-8"),
                          capture_output=True, cwd=tempfile.gettempdir(), check=False, timeout=180,
                          env={**os.environ, "QLAUDIFIED_NESTED": "1"})
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace"))
    except ValueError:
        return None
    out = (data.get("structured_output") or {}).get("facts")
    if not isinstance(out, list):
        return None
    by_n = {int(x.get("n", -1)): x for x in out if isinstance(x, dict)}
    rows = []
    for n, fact in enumerate(facts, 1):
        x = by_n.get(n, {})
        certainty = x.get("certainty") if x.get("stated") else "not stated"
        rows.append({"fact": fact["id"], "certainty": certainty})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/v2/judge.py")
    parser.add_argument("--set", dest="run_set", required=True,
                        choices=["dry", "pilot", "confirmatory"])
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-runs", type=int)
    args = parser.parse_args(argv)
    root = REPO / "eval" / "runs" / args.run_set / "v2"
    cache_path = root / "judge.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            cache[(rec["run"], rec["answer_sha"])] = rec
    judged = 0
    for folder in sorted(p for p in root.glob("*") if (p / "result.json").exists()):
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        if result.get("returncode") != 0:
            continue
        sha = hashlib.sha256((result.get("result") or "").encode()).hexdigest()[:16]
        if (folder.name, sha) in cache:
            continue
        if args.max_runs is not None and judged >= args.max_runs:
            break
        task = json.loads((HERE / "tasks" / f"{result['task']}.json").read_text(encoding="utf-8"))
        rows = judge_run(result, task, args.model, seed=int(sha, 16) % 10 ** 6)
        if rows is None:
            print(f"{folder.name}: judge call failed")
            continue
        with open(cache_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"run": folder.name, "answer_sha": sha, "model": args.model,
                                "facts": rows}) + "\n")
        judged += 1
        print(f"judged {folder.name}")
    print(f"{judged} runs judged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
