"""Blind export of handoff answers for hand labelling.

    python blind.py <repo> <outdir>

Writes <outdir>/answers.md (random IDs; no condition, variant or repeat) and <outdir>/key.json
(ID -> run folder), to open only after labelling. Per answer: each focus intervention's text
(from a mention of its name to the next intervention's), tagged with its source kind, plus any
other line that mentions hedging, caveats, uncertainty or the abstracts.
"""

import json
import random
import re
import sys
from pathlib import Path

repo, outdir = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / "eval" / "handoff"))
import score

META = re.compile(r"hedg|caveat|uncertain|abstract|qualif|tentative|not established", re.IGNORECASE)
runs = []
for folder in sorted((repo / "eval/runs/dry/handoff").glob("*")):
    task, variant, condition, rep, _ = folder.name.split("__")
    if variant == "prep" or rep not in ("r1", "r2") or condition not in (
            "off", "prompt", "placebo", "medium"):
        continue
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    if result.get("returncode") == 0:
        runs.append((folder, task, result.get("result") or ""))
rng = random.Random(20261021)
rng.shuffle(runs)
outdir.mkdir(parents=True, exist_ok=True)
key, parts = {}, []
for n, (folder, task, answer) in enumerate(runs, 1):
    rid = f"X{n:03d}"
    key[rid] = folder.name
    meta = json.loads((repo / "eval/handoff/tasks" / f"{task}.json").read_text(encoding="utf-8"))
    names = [i["name"] for i in meta["interventions"]]
    segs = score.stretches(answer, names)
    lines = [f"## {rid}"]
    for i in [i for i in meta["interventions"] if i["focus"]]:
        text = " ".join(segs.get(i["name"], "").split())
        lines.append(f"- [{i['kind'][0].upper()}] {i['name']}: {text[:330] or '(not mentioned)'}")
    shown = " ".join(segs.values())
    extra = [ln.strip() for ln in answer.splitlines()
             if META.search(ln) and ln.strip() and ln.strip()[:60] not in shown]
    for ln in extra[:4]:
        lines.append(f"  · {ln[:300]}")
    parts.append("\n".join(lines))
(outdir / "answers.md").write_text("\n\n".join(parts) + "\n", encoding="utf-8")
(outdir / "key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
print(f"{len(runs)} answers blinded to {outdir}")
