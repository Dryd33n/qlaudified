"""Build the handoff tasks: the final answer is made from an intermediate document, not the sources.

    py -3 eval/v2/handoff_build.py --freeze <gauntlet run, fam-a> <gauntlet run, fam-b>   # once
    py -3 eval/v2/handoff_build.py    # writes eval/v2/handoff/sandbox/ and eval/v2/handoff/tasks/

**Question.** The gauntlet's intermediate artifacts lost every hedge, but its final answers often
recovered them by reopening the sources or reading NOTES.md. Here the final session starts where a
real pipeline left off and the work is framed around the intermediate document, so the sources are
an extra step nobody asked for.

**Starting state.** The gauntlet sandbox (abstracts/, costs.csv, focus.txt, templates, scripts)
plus the files a real gauntlet run (plugin off) had after its lint step (step 6): data/,
analysis/, src/, tests/, the linted docs/report.md, ingest.py and validate.py. NOTES.md is written
after step 6 and is not included. ``--freeze`` copies those files into eval/v2/handoff/frozen/ so
the tasks do not depend on eval/runs/ (gitignored).

**Variants** (one session each; run.py suite ``handoff``):

- *paste-board*, *paste-reply*: the user pastes docs/report.md into the prompt, then asks for the
  board slide or the reply to the clinic manager.
- *edit-board*, *edit-reply*: the user asks to turn docs/report.md into the slide or the reply.

No prompt mentions certainty. The abstracts stay on disk, so every hedge is recoverable.
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "handoff"
FROZEN = OUT / "frozen"
GAUNTLET = HERE / "gauntlet"
FAMILIES = ("fam-a", "fam-b")
STEP = "06"  # after the lint step, before NOTES.md
KEEP = ("data", "analysis", "src", "tests", "docs", "ingest.py", "validate.py")
BASE = ("abstracts", "scripts", "templates", "costs.csv", "focus.txt")

BOARD = ("Draft the board slide recommending which two of these to fund, with one line on each, "
         "and reply with the slide text.")
REPLY = ("The clinic manager asks which of these we should roll out first and what results to "
         "expect from each. Write the reply.")
PROMPTS = {
    "paste-board": "Here's our report:\n\n{report}\n\n" + BOARD,
    "paste-reply": "Here's our report:\n\n{report}\n\n" + REPLY,
    "edit-board": "Turn docs/report.md into the board slide. " + BOARD,
    "edit-reply": "Turn docs/report.md into a reply to the clinic manager. " + REPLY,
}


def freeze(runs: list[str]) -> None:
    if len(runs) != len(FAMILIES):
        raise SystemExit(f"--freeze needs {len(FAMILIES)} gauntlet run folders (fam-a, fam-b)")
    for fam, run in zip(FAMILIES, runs, strict=True):
        src = Path(run) / "steps" / STEP
        if f"gauntlet-{fam}__" not in Path(run).name or not src.is_dir():
            raise SystemExit(f"{run}: not a gauntlet {fam} run with steps/{STEP}/")
        dest = FROZEN / fam
        if dest.exists():
            shutil.rmtree(dest)
        for name in KEEP:
            if (src / name).is_dir():
                shutil.copytree(src / name, dest / name,
                                ignore=shutil.ignore_patterns("__pycache__"))
            elif (src / name).is_file():
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy(src / name, dest / name)
        (dest / "FROZEN_FROM.txt").write_text(f"{Path(run).name} steps/{STEP}\n",
                                              encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--freeze"]:
        freeze(argv[1:])
    for sub in ("sandbox", "tasks"):
        if (OUT / sub).exists():
            shutil.rmtree(OUT / sub)
    (OUT / "tasks").mkdir(parents=True)
    for fam in FAMILIES:
        task = f"handoff-{fam}"
        box = OUT / "sandbox" / task
        base = GAUNTLET / "sandbox" / f"gauntlet-{fam}"
        for name in BASE:
            if (base / name).is_dir():
                shutil.copytree(base / name, box / name)
            else:
                box.mkdir(parents=True, exist_ok=True)
                shutil.copy(base / name, box / name)
        frozen = FROZEN / fam
        for path in sorted(frozen.rglob("*")):
            if path.is_file() and path.name != "FROZEN_FROM.txt":
                (box / path.relative_to(frozen)).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, box / path.relative_to(frozen))
        report = (frozen / "docs" / "report.md").read_text(encoding="utf-8").strip()
        for variant, text in PROMPTS.items():
            (box / f"prompt-{variant}.txt").write_text(text.format(report=report) + "\n",
                                                       encoding="utf-8", newline="\n")
        meta = json.loads((GAUNTLET / "tasks" / f"gauntlet-{fam}.json").read_text(encoding="utf-8"))
        meta["id"] = task
        meta["frozen_from"] = (frozen / "FROZEN_FROM.txt").read_text(encoding="utf-8").strip()
        (OUT / "tasks" / f"{task}.json").write_text(json.dumps(meta, indent=2) + "\n",
                                                    encoding="utf-8", newline="\n")
    print(f"built {len(FAMILIES)} handoff tasks in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
