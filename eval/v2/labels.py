"""Blind human labels and scorer agreement for study v2 (methods critique, fix 9).

    py -3 eval/v2/labels.py make --set pilot --n 50 --sheet labels.csv --key labels-key.csv
    py -3 eval/v2/labels.py agree --set pilot --sheet labels.csv --key labels-key.csv

**make** samples (answer, fact) items across conditions, half from hedged facts and half from
firm ones, strips plugin markers, shuffles them and writes two files: the sheet to label (item
number, answer, fact, what the source says, and empty ``stated`` and ``certainty`` columns) and a
key that maps items to runs and conditions. Label the sheet without opening the key.

Fill ``stated`` with y or n, and ``certainty`` with hedged or firm when stated.

**agree** reads the filled sheet and reports Cohen's kappa for the rule scorer (calib.py) and, if
judge.jsonl exists, the LLM judge, each against the human labels, on three categories: hedged,
firm, not stated.
"""

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import calib
import judge

CATEGORIES = ("hedged", "firm", "not stated")


def _runs(run_set: str) -> list[tuple[Path, dict, dict]]:
    root = REPO / "eval" / "runs" / run_set / "v2"
    out = []
    for folder in sorted(p for p in root.glob("*") if (p / "result.json").exists()):
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        if result.get("returncode") == 0:
            task = json.loads((HERE / "tasks" / f"{result['task']}.json").read_text(encoding="utf-8"))
            out.append((folder, result, task))
    return out


def make(run_set: str, n: int, sheet: Path, key: Path, seed: int = 2026) -> None:
    rng = random.Random(seed)
    pool: dict[bool, list] = {True: [], False: []}
    for folder, result, task in _runs(run_set):
        for fact in task["facts"]:
            pool[bool(fact["hedged"])].append((folder.name, result, task, fact))
    picked = []
    for hedged in (True, False):
        rng.shuffle(pool[hedged])
        picked += pool[hedged][: n // 2 + (n % 2 if hedged else 0)]
    rng.shuffle(picked)
    with open(sheet, "w", newline="", encoding="utf-8") as s, \
            open(key, "w", newline="", encoding="utf-8") as k:
        ws, wk = csv.writer(s), csv.writer(k)
        ws.writerow(["item", "answer", "fact", "source_says", "stated", "certainty"])
        wk.writerow(["item", "run", "condition", "variant", "fact"])
        for i, (run, result, task, fact) in enumerate(picked, 1):
            answer = calib.strip_plugin_text(result.get("result") or "").strip()
            ws.writerow([i, answer, fact["label"], judge.source_statement(task, fact), "", ""])
            wk.writerow([i, run, result["condition"], result["variant"], fact["id"]])
    print(f"wrote {len(picked)} items to {sheet} (key: {key}; don't open it while labelling)")


def _category(stated: bool, hedged: bool) -> str:
    return CATEGORIES[0] if stated and hedged else CATEGORIES[1] if stated else CATEGORIES[2]


def kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[c] * cb[c] for c in CATEGORIES) / n ** 2
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def agree(run_set: str, sheet: Path, key: Path) -> None:
    with open(key, encoding="utf-8") as f:
        keys = {r["item"]: r for r in csv.DictReader(f)}
    with open(sheet, encoding="utf-8") as f:
        labelled = list(csv.DictReader(f))
    runs = {folder.name: (result, task) for folder, result, task in _runs(run_set)}
    judge_path = REPO / "eval" / "runs" / run_set / "v2" / "judge.jsonl"
    judged = {}
    if judge_path.exists():
        for line in judge_path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            judged[rec["run"]] = {f["fact"]: f["certainty"] for f in rec["facts"]}
    human, rules, llm, llm_human = [], [], [], []
    for row in labelled:
        stated = row["stated"].strip().lower()
        if stated not in ("y", "n"):
            continue
        h = _category(stated == "y", row["certainty"].strip().lower() == "hedged")
        k = keys[row["item"]]
        result, task = runs[k["run"]]
        score = next(s for s in calib.score_answer(result.get("result") or "", task["facts"])
                     if s.fact == k["fact"])
        human.append(h)
        rules.append(_category(score.stated, score.hedged_answer))
        if k["run"] in judged and k["fact"] in judged[k["run"]]:
            llm.append(judged[k["run"]][k["fact"]])
            llm_human.append(h)
    print(f"{len(human)} labelled items")
    print(f"rule scorer vs human: kappa = {kappa(rules, human):.2f}, "
          f"agreement {sum(a == b for a, b in zip(rules, human, strict=True))}/{len(human)}")
    if llm:
        print(f"LLM judge vs human:   kappa = {kappa(llm, llm_human):.2f} on {len(llm)} items")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/v2/labels.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("make", "agree"):
        p = sub.add_parser(name)
        p.add_argument("--set", dest="run_set", required=True,
                       choices=["dry", "pilot", "confirmatory"])
        p.add_argument("--sheet", required=True)
        p.add_argument("--key", required=True)
        if name == "make":
            p.add_argument("--n", type=int, default=50)
    args = parser.parse_args(argv)
    if args.cmd == "make":
        make(args.run_set, args.n, Path(args.sheet), Path(args.key))
    else:
        agree(args.run_set, Path(args.sheet), Path(args.key))
    return 0


if __name__ == "__main__":
    sys.exit(main())
