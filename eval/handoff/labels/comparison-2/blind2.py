"""Blind export for comparison 2: every answer's text per focus intervention, uncut.

    python blind2.py <repo> <outdir>

Comparison 1's export cut each intervention's text at 330 characters and hid hedge notes. Here
each focus intervention's stretch is shown whole, followed by every other line of the answer
that mentions hedging, estimates or the sources, also whole. Random IDs; no condition, variant,
repeat or family shown beyond the six focus interventions and their kinds.
"""

import json
import random
import re
import sys
from pathlib import Path

repo, outdir = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / "eval" / "handoff"))
import score

META = re.compile(r"hedg|caveat|uncertain|estimat|tentativ|abstract|qualif|provisional|"
                  r"may have|possibly|roughly|appeared|less certain|guarantee|firm", re.IGNORECASE)
runs = []
for folder in sorted((repo / "eval/runs/pilot/handoff").glob("*")):
    task, variant, condition, rep, _ = folder.name.split("__")
    if variant == "prep" or rep not in ("r1", "r2"):
        continue
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    if result.get("returncode") == 0:
        runs.append((folder, task, result.get("result") or ""))
rng = random.Random(20261022)
rng.shuffle(runs)
outdir.mkdir(parents=True, exist_ok=True)
key, parts = {}, []
for n, (folder, task, answer) in enumerate(runs, 1):
    rid = f"Y{n:03d}"
    key[rid] = folder.name
    meta = json.loads((repo / "eval/handoff/tasks" / f"{task}.json").read_text(encoding="utf-8"))
    segs = score.stretches(answer, [i["name"] for i in meta["interventions"]])
    lines = [f"## {rid}"]
    for i in [i for i in meta["interventions"] if i["focus"]]:
        text = " ".join(segs.get(i["name"], "").split())
        lines.append(f"- [{i['kind'][0].upper()}] {i['name']}: {text or '(not mentioned)'}")
    shown = " ".join(" ".join(s.split()) for s in segs.values())
    for ln in answer.splitlines():
        s = " ".join(ln.split())
        if s and META.search(s) and s not in shown:
            lines.append(f"  · {s}")
    parts.append("\n".join(lines))
(outdir / "answers.md").write_text("\n\n".join(parts) + "\n", encoding="utf-8")
(outdir / "key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
print(f"{len(runs)} answers blinded to {outdir}")
