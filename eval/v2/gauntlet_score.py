"""Score gauntlet runs: which channel loses the hedge?

    py -3 eval/v2/gauntlet_score.py --set dry

run.py keeps each step's files (``steps/NN/``) and the final answer. Per stage:

- **ingest**, **tidy**: data/findings.json, every record. A hedged study's record is **kept** if any
  value (caveats or another field) carries a hedge cue, else **inflated**; a firm study's record is
  **deflated** if it carries one. Also counted: records with a non-empty ``caveats``.
- **rank**, **code**: analysis/ranking.csv and src/recommend.py, every intervention. The text from
  an intervention's name to the next intervention's name is its stretch.
- **report**, **lint**, **notes**, **answer**: docs/report.md before and after the linter,
  NOTES.md and the read-back answer, the focus interventions only. A stretch of fewer than four
  words is **omitted**.
- **reopened**: sessions after the first whose tool calls targeted abstracts/ (non-write calls),
  split into **read** (Read, Grep showing lines, or a shell command that prints file text: cat,
  grep, head, Get-Content, a python one-liner) and **listed** (ls, wc, grep -l/-c).

The cue lexicon is hops_score.cues (study v2's list plus scientific hedges). It counts commentary
and "about" as a preposition, so read cells by hand before trusting a number (see hop-study.md).
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import hops_score

TASKS = HERE / "gauntlet" / "tasks"
RUNS = REPO / "eval" / "runs"
STAGES = [  # (name, step, file, scope)
    ("ingest", 1, "data/findings.json", "records"),
    ("tidy", 2, "data/findings.json", "records"),
    ("rank", 3, "analysis/ranking.csv", "all"),
    ("code", 4, "src/recommend.py", "all"),
    ("report", 5, "docs/report.md", "focus"),
    ("lint", 6, "docs/report.md", "focus"),
    ("notes", 7, "NOTES.md", "focus"),
    ("answer", None, None, "focus"),
]
MIN_WORDS = 3


def stretches(text: str, names: list[str]) -> dict[str, str]:
    """Each name's text: from a mention to the next mention of a different name."""
    marks = sorted((m.start(), name) for name in names
                   for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.IGNORECASE))
    found: dict[str, list[str]] = defaultdict(list)
    for n, (start, name) in enumerate(marks):
        if n and marks[n - 1][1] == name:
            continue
        end = next((s for s, other in marks[n + 1:] if other != name), len(text))
        found[name].append(text[start:end])
    return {name: " ".join(parts) for name, parts in found.items()}


def outcome(kind: str, stretch: str | None, prose: bool) -> str:
    if stretch is None or (prose and len(re.findall(r"[A-Za-z]{2,}", stretch)) <= MIN_WORDS):
        return "omitted"
    hedged = bool(hops_score.cues(stretch))
    if kind == "hedged":
        return "kept" if hedged else "inflated"
    return "deflated" if hedged else "plain"


def score_records(text: str, task: dict) -> tuple[list[tuple[str, str]], int]:
    """(kind, outcome) per study and the number of records with non-empty caveats."""
    try:
        records = {r.get("id"): r for r in json.loads(text)}
    except (ValueError, AttributeError, TypeError):
        records = {}
    cells, caveats = [], 0
    for s in task["studies"]:
        rec = records.get(s["id"])
        if rec is None:
            cells.append((s["kind"], "omitted"))
            continue
        caveats += bool(str(rec.get("caveats") or "").strip())
        values = " | ".join(str(v) for k, v in rec.items()  # " | ": "17 may" reads as a date
                             if k not in ("id", "intervention"))
        cells.append((s["kind"], outcome(s["kind"], values, prose=False)))
    return cells, caveats


def score_text(text: str, task: dict, scope: str, prose: bool) -> list[tuple[str, str]]:
    items = [i for i in task["interventions"] if scope == "all" or i["focus"]]
    segs = stretches(text, [i["name"] for i in task["interventions"]])
    return [(i["kind"], outcome(i["kind"], segs.get(i["name"]), prose)) for i in items]


_SHELL_READ = re.compile(r"\b(cat|head|tail|grep|egrep|sed|awk|less|more|type|py|python|"
                         r"Get-Content|gc|Select-String|sls)\b", re.IGNORECASE)
_LIST_ONLY = re.compile(r"\bgrep\s+-[a-zA-Z]*[lLc]|\|\s*wc\b")


def _abstract_access(use: dict) -> str | None:
    """"read" if a tool call can show an abstract's text, "listed" if it only touches the folder."""
    given = use.get("input") or {}
    target = " ".join(str(given.get(k, "")) for k in hops_score.TARGETS).replace("\\", "/")
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


def access(folder: Path) -> dict[int, str]:
    """Per session after the first (1-based): "read" or "listed" (abstracts/), absent if neither."""
    out: dict[int, str] = {}
    for n, path in enumerate(sorted(folder.glob("transcript-*.jsonl"))[1:], 2):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                content = (json.loads(line).get("message") or {}).get("content") or []
            except (ValueError, AttributeError):
                continue
            for use in content if isinstance(content, list) else []:
                if (not isinstance(use, dict) or use.get("type") != "tool_use"
                        or use.get("name") in hops_score.WRITES):
                    continue
                kind = _abstract_access(use)
                if kind == "read" or (kind and n not in out):
                    out[n] = kind
    return out


def reopened(folder: Path) -> list[int]:
    """Sessions after the first (1-based) whose non-write tool calls targeted abstracts/."""
    return sorted(access(folder))


def score_run(folder: Path, task: dict) -> dict:
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    stages = {}
    for name, step, rel, scope in STAGES:
        if step is None:
            text = result.get("result") or ""
        else:
            path = folder / "steps" / f"{step:02d}" / rel
            text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        if scope == "records":
            cells, caveats = score_records(text, task)
            stages[name] = {"cells": cells, "caveats": caveats}
        else:
            stages[name] = {"cells": score_text(text, task, scope, prose=scope == "focus")}
    seen = access(folder)
    last = len(sorted(folder.glob("transcript-*.jsonl")))
    return {"task": result["task"], "variant": result.get("variant", "?"),
            "cost": result.get("total_cost_usd", 0.0), "turns": result.get("num_turns", 0),
            "stages": stages, "reopened": sorted(seen),
            "read": sorted(n for n, k in seen.items() if k == "read"),
            "final": seen.get(last, "no") if last > 1 else "no"}


def _rate(num: int, den: int) -> str:
    return f"{100 * num / den:.0f}% ({num}/{den})" if den else "n/a"


def report(runs: list[dict]) -> str:
    out = ["| Stage | Hedged kept (of stated) | Firm deflated (of stated) | Omitted | Caveats filled |",
           "| --- | --- | --- | --- | --- |"]
    for name, *_ in STAGES:
        cells = [c for r in runs for c in r["stages"][name]["cells"]]
        kept = sum(o == "kept" for _, o in cells)
        infl = sum(o == "inflated" for _, o in cells)
        defl = sum(o == "deflated" for _, o in cells)
        plain = sum(o == "plain" for _, o in cells)
        om = sum(o == "omitted" for _, o in cells)
        cav = (str(sum(r["stages"][name]["caveats"] for r in runs))
               if "caveats" in runs[0]["stages"][name] else "")
        out.append(f"| {name} | {_rate(kept, kept + infl)} | {_rate(defl, defl + plain)} | "
                   f"{_rate(om, len(cells))} | {cav} |")
    out += ["", "## Final answer by read-back question", "",
            ("| Variant | Runs | Hedged kept (of stated) | Firm deflated (of stated) | Omitted "
             "| Last session read abstracts |"), "| --- | --- | --- | --- | --- | --- |"]
    for variant in sorted({r["variant"] for r in runs}):
        group = [r for r in runs if r["variant"] == variant]
        cells = [c for r in group for c in r["stages"]["answer"]["cells"]]
        kept, infl = (sum(o == k for _, o in cells) for k in ("kept", "inflated"))
        defl, plain = (sum(o == k for _, o in cells) for k in ("deflated", "plain"))
        reads = sum(r["final"] == "read" for r in group)
        out.append(f"| {variant} | {len(group)} | {_rate(kept, kept + infl)} | "
                   f"{_rate(defl, defl + plain)} | "
                   f"{_rate(sum(o == 'omitted' for _, o in cells), len(cells))} | "
                   f"{reads}/{len(group)} |")
    out += ["", "| Run | Cost | Turns | Sessions that read abstracts/ | Only listed it |",
            "| --- | --- | --- | --- | --- |"]
    out += [f"| {r['task']} {r['variant']} | ${r['cost']:.4f} | {r['turns']} | "
            f"{r['read'] or 'none'} | {sorted(set(r['reopened']) - set(r['read'])) or 'none'} |"
            for r in runs]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/v2/gauntlet_score.py")
    parser.add_argument("--set", dest="run_set", default="dry")
    args = parser.parse_args(argv)
    runs = []
    for folder in sorted((RUNS / args.run_set / "gauntlet").glob("*")):
        result = folder / "result.json"
        if not result.exists() or json.loads(result.read_text(encoding="utf-8")).get("returncode"):
            continue
        task = json.loads((TASKS / f"{folder.name.split('__')[0]}.json").read_text(encoding="utf-8"))
        runs.append(score_run(folder, task))
    if not runs:
        print(f"no finished runs in {RUNS / args.run_set / 'gauntlet'}")
        return 1
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(report(runs), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
