"""Build the study v2 tasks from eval/v2/families/*.toml (methods critique, fixes 2, 4, 5).

    py -3 eval/v2/build.py            # write eval/v2/sandbox/, eval/v2/tasks/, eval/v2/MANIFEST.json
    py -3 eval/v2/build.py --check    # exit 1 if the committed output differs (frozen task set)

Each family becomes two tasks:

- ``<family>-near``: read the source, say so in one line, then the question.
- ``<family>-far``: read the source, then the organisation's eight distractor documents two at a
  time, each answered in one line, then the question. Distance is reported in tokens (chars / 4 of
  what was read in between), not steps.

Each task has three prompt styles, analysed separately (fix 2): **natural** (the open question),
**format** (the same question with a format constraint: a two-column table or one slide line) and
**antihedge** (the format constraint plus "state the figures plainly, with no hedging").

Before writing anything the families are validated: every fact's value appears in its source
documents, no two facts in a family share a value, and no fact's value appears in any distractor
document, so the scorer can tell which fact an answer states.
"""

import argparse
import hashlib
import json
import shutil
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import figures

FAMILIES = HERE / "families"
SANDBOX = HERE / "sandbox"
TASKS = HERE / "tasks"
MANIFEST = HERE / "MANIFEST.json"

FORMATS = {
    "table": "Answer only with a markdown table with columns Item and Value, nothing else.",
    "slide": "Keep it to one short line for a slide.",
}
ANTIHEDGE = "State the figures plainly, with no hedging."
STYLES = ("natural", "format", "antihedge")
LONG = "operating-report.md"  # read on its own, last, in every far task


def load_families() -> list[dict]:
    out = []
    for path in sorted(FAMILIES.glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for i, fam in enumerate(data["family"]):
            docs = dict(fam["docs"])
            read = docs.pop("read", None)  # `read = [...]` written under [family.docs]
            fam = {**fam, "docs": docs, "org": data["org"], "org_file": path.stem, "index": i,
                   "distractors": data["distractors"]}
            fam["read"] = fam.get("read") or read or list(docs)
            out.append(fam)
    return out


def _states(text: str, fact: dict) -> bool:
    return any(figures.matches(f, fact["value"], fact["unit"]) for f in figures.extract(text))


def _render(fact: dict) -> str:
    """The fact's value as an answer would write it, for the overlap check."""
    v = fact["value"]
    if fact["unit"] == "date":
        return str(v)
    if fact["unit"] == "%":
        return f"{v}%"
    return f"${v:,}" if fact["unit"] == "USD" else f"{v:,}"


def validate(fam: dict) -> list[str]:
    problems = []
    source = "\n".join(fam["docs"].values())
    for fact in fam["facts"]:
        if not _states(source, fact):
            problems.append(f"{fam['id']}/{fact['id']}: value {fact['value']} not found in sources")
        for name, doc in fam["distractors"].items():
            if _states(doc, fact):
                problems.append(f"{fam['id']}/{fact['id']}: value {fact['value']} also in {name}")
        if fact["hedged"] and not fact.get("cue"):
            problems.append(f"{fam['id']}/{fact['id']}: hedged fact without a cue")
    for fact in fam["facts"]:
        for other in fam["facts"]:
            if other is not fact and _states(_render(other), fact):
                problems.append(f"{fam['id']}: {other['id']} would be scored as {fact['id']}")
    if not any(f["hedged"] for f in fam["facts"]) or all(f["hedged"] for f in fam["facts"]):
        problems.append(f"{fam['id']}: needs both hedged and firm facts")
    return problems


def _names(files: list[str]) -> str:
    return files[0] if len(files) == 1 else ", ".join(files[:-1]) + " and " + files[-1]


def prompts(fam: dict, far: bool) -> tuple[dict[str, str], list[str], int]:
    """Prompt files per style (steps separated by ---), the distractors read, nominal tokens."""
    read = fam["read"]
    first = f"Read {_names(read)} and tell me in one line that you have read {'it' if len(read) == 1 else 'them'}."
    steps = [first]
    order: list[str] = []
    if far:
        names = sorted(n for n in fam["distractors"] if n != LONG)
        shift = (2 * fam["index"]) % len(names)
        order = names[shift:] + names[:shift]
        for a, b in zip(order[::2], order[1::2], strict=True):
            steps.append(f"Read {a} and {b} and tell me each file's main point in one line.")
        if LONG in fam["distractors"]:
            order.append(LONG)
            steps.append(f"Read {LONG} and tell me its three main points, one line each.")
    ask = f"From what you read earlier, {fam['ask']}."
    constraint = FORMATS[fam["format"]]
    finals = {"natural": ask, "format": f"{ask} {constraint}",
              "antihedge": f"{ask} {constraint} {ANTIHEDGE}"}
    tokens = sum(len(fam["distractors"][n]) for n in order) // 4
    return ({s: "\n---\n".join([*steps, finals[s]]) + "\n" for s in STYLES}, order, tokens)


def build(out_sandbox: Path = SANDBOX, out_tasks: Path = TASKS) -> dict[str, str]:
    families = load_families()
    problems = [p for fam in families for p in validate(fam)]
    if problems:
        raise SystemExit("invalid families:\n  " + "\n  ".join(problems))
    for folder in (out_sandbox, out_tasks):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
    written: dict[str, str] = {}

    def write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        root, name = (out_sandbox, "sandbox") if path.is_relative_to(out_sandbox) else (out_tasks, "tasks")
        written[f"{name}/{path.relative_to(root).as_posix()}"] = hashlib.sha256(text.encode()).hexdigest()

    for fam in families:
        for distance in ("near", "far"):
            task = f"{fam['id']}-{distance}"
            files, order, tokens = prompts(fam, distance == "far")
            for name, text in fam["docs"].items():
                write(out_sandbox / task / name, text.lstrip("\n"))
            for name in order:
                write(out_sandbox / task / name, fam["distractors"][name].lstrip("\n"))
            for style, text in files.items():
                write(out_sandbox / task / f"prompt-{style}.txt", text)
            meta = {
                "id": task, "family": fam["id"], "org": fam["org"], "scope": fam["scope"],
                "format": fam["format"], "distance": distance, "distance_tokens": tokens,
                "sources": list(fam["docs"]), "read": fam["read"], "distractors": order,
                "facts": [{**f, "label": f["label"]} for f in fam["facts"]],
            }
            write(out_tasks / f"{task}.json", json.dumps(meta, indent=2) + "\n")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/v2/build.py")
    parser.add_argument("--check", action="store_true",
                        help="rebuild in a temp folder and compare with the committed output")
    args = parser.parse_args(argv)
    if args.check:
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="qlaudified-v2-"))
        try:
            fresh = build(tmp / "sandbox", tmp / "tasks")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        committed = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
        if fresh != committed:
            diff = sorted(set(fresh.items()) ^ set(committed.items()))
            print("task set differs from MANIFEST.json:\n  " + "\n  ".join(k for k, _ in diff[:20]))
            return 1
        print(f"task set matches MANIFEST.json ({len(committed)} files)")
        return 0
    written = build()
    families = sorted({k.split("/")[1].rsplit("-", 1)[0] for k in written if k.startswith("tasks/")})
    MANIFEST.write_text(json.dumps({"families": families, "files": dict(sorted(written.items()))},
                                   indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"built {len(families)} families, {sum(k.startswith('tasks/') for k in written)} tasks, "
          f"{len(written)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
