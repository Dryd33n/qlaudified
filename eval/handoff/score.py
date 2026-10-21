"""Score handoff runs: does an answer made from the intermediate report keep the sources' hedges?

    py -3 eval/handoff/score.py --set dry

One session per run. The answer is split per focus intervention (from a mention of its name to
the next mention of another intervention) and judged against the sources' kind:

- hedged intervention: **kept** (its text carries a hedge cue), **inflated** (stated plainly) or
  **omitted** (not mentioned, or fewer than four words);
- firm intervention: **plain**, **deflated** (stated with a hedge) or **omitted**.

The transcript shows what the session opened: an abstract (the sources), data/findings.json, or
neither. The lexicon (cues.py) counts commentary ("the board may ask") and an answer that names an
intervention without stating any effect, so read the cells by hand before trusting a number.
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import cues

TASKS = HERE / "tasks"
RUNS = REPO / "eval" / "runs"
MIN_WORDS = 3
WRITES = ("Write", "Edit", "MultiEdit", "NotebookEdit")
TARGETS = ("file_path", "path", "pattern", "command", "notebook_path")
_SHELL_READ = re.compile(r"\b(cat|head|tail|grep|egrep|sed|awk|less|more|type|py|python|"
                         r"Get-Content|gc|Select-String|sls)\b", re.IGNORECASE)
_LIST_ONLY = re.compile(r"\bgrep\s+-[a-zA-Z]*[lLc]|\|\s*wc\b")


def stretches(text: str, names: list[str]) -> dict[str, str]:
    """Each name's text: from a mention to the next mention of a different name."""
    marks = sorted((m.start(), name) for name in names
                   for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text,
                                        re.IGNORECASE))
    found: dict[str, list[str]] = {}
    for n, (start, name) in enumerate(marks):
        if n and marks[n - 1][1] == name:
            continue
        end = next((s for s, other in marks[n + 1:] if other != name), len(text))
        found.setdefault(name, []).append(text[start:end])
    return {name: " ".join(parts) for name, parts in found.items()}


def outcome(kind: str, stretch: str | None) -> str:
    if stretch is None or len(re.findall(r"[A-Za-z]{2,}", stretch)) <= MIN_WORDS:
        return "omitted"
    hedged = bool(cues.find(stretch))
    if kind == "hedged":
        return "kept" if hedged else "inflated"
    return "deflated" if hedged else "plain"


def score_answer(text: str, task: dict) -> list[tuple[str, str]]:
    """(kind, outcome) per focus intervention."""
    segs = stretches(text, [i["name"] for i in task["interventions"]])
    return [(i["kind"], outcome(i["kind"], segs.get(i["name"])))
            for i in task["interventions"] if i["focus"]]


def abstract_access(use: dict) -> str | None:
    """"read" if a tool call can show an abstract's text, "listed" if it only touches the folder."""
    given = use.get("input") or {}
    target = " ".join(str(given.get(k, "")) for k in TARGETS).replace("\\", "/")
    if "abstracts" not in target:
        return None
    name = use.get("name")
    if name == "Read":
        return "read"
    if name == "Grep":
        return "listed" if given.get("output_mode") in ("files_with_matches", "count") else "read"
    if name in ("Bash", "PowerShell"):
        # A pipeline reads text if its first command does: "ls abstracts | head" only lists.
        parts = re.split(r"&&|\|\||;|\n", str(given.get("command", "")))
        return ("read" if any("abstracts" in part and _SHELL_READ.match(part.split("|")[0].strip())
                              and not _LIST_ONLY.search(part) for part in parts) else "listed")
    return "listed"


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
            if abstract_access(use) == "read":
                seen["abstracts"] = True
            given = json.dumps(use.get("input") or {}).replace("\\\\", "/")
            if "findings.json" in given and use.get("name") not in WRITES:
                seen["findings"] = True
    return seen


def score_run(folder: Path, task: dict) -> dict:
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    return {"task": result["task"], "variant": result.get("variant", "?"),
            "condition": result.get("condition", "?"),
            "cost": result.get("total_cost_usd", 0.0), "turns": result.get("num_turns", 0),
            "cells": score_answer(result.get("result") or "", task),
            **opened(folder / "transcript.jsonl")}


def _rate(num: int, den: int) -> str:
    return f"{100 * num / den:.0f}% ({num}/{den})" if den else "n/a"


def report(runs: list[dict]) -> str:
    out = [("| Condition | Variant | Runs | Hedged kept (of stated) | Firm deflated (of stated) "
            "| Omitted | Read an abstract | Read findings.json |"),
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for key in sorted({(r["condition"], r["variant"]) for r in runs}):
        group = [r for r in runs if (r["condition"], r["variant"]) == key]
        cells = [c for r in group for c in r["cells"]]
        kept, infl, defl, plain, om = (sum(o == k for _, o in cells) for k in
                                       ("kept", "inflated", "deflated", "plain", "omitted"))
        out.append(f"| {key[0]} | {key[1]} | {len(group)} | {_rate(kept, kept + infl)} | "
                   f"{_rate(defl, defl + plain)} | {_rate(om, len(cells))} | "
                   f"{sum(r['abstracts'] for r in group)}/{len(group)} | "
                   f"{sum(r['findings'] for r in group)}/{len(group)} |")
    out += ["", "| Run | Cost | Turns |", "| --- | --- | --- |"]
    out += [f"| {r['task']} {r['variant']} {r['condition']} | ${r['cost']:.4f} | {r['turns']} |"
            for r in runs]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/handoff/score.py")
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
