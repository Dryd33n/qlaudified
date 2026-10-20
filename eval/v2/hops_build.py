"""Build the hop study: real findings relayed through 4, 6, 8 or 10 hops.

    py -3 eval/v2/hops_build.py    # writes eval/v2/hops/sandbox/ and eval/v2/hops/tasks/

**Question.** Does a finding keep its source's certainty as an agent moves it through more hops?
Sources are real scientific findings with human certainty labels (Pei & Jurgens, EMNLP 2021;
pool built by hops_select.py), so neither the hedges nor the ground truth are written here.

**A hop** is one step in which the agent reads the previous artifact and writes the finding into a
new one. The chain for N hops is fixed at both ends so that only its length changes:

- hop 1: read every file in studies/ and write notes (``hops/01-notes.md``);
- hops 2..N-1: N-2 re-encodings from the menu below (a CSV table, one-liners, slide bullets, ...);
- hop N: a briefing for a science policy adviser (always the same final genre).

Every step names one input file and one output file, so the optimal solution takes exactly N
hops (one read and one write each). Every artifact keeps each study's ID, which is how the scorer
finds a study at every hop (hops_score.py).

**Families.** Four reading lists of six studies (three hedged, three firm, in shuffled order),
disjoint and drawn with a fixed seed. The middle menu is rotated by two places per family, so a
hop kind sits at different positions across families and position is not confounded with kind.
The N-hop chain of a family is the first N-2 kinds of its rotated menu, so longer chains extend
shorter ones.

**Variants** (same steps, different session boundaries; run.py suite ``hops``):

- *relay*: every hop starts a fresh session (``/new``), so the sources and earlier artifacts are
  out of context unless Claude reopens them. The case the plugin's refeed is for.
- *session*: every hop in one session, as in the v1 and v2 tasks; the sources stay in context.
"""

import itertools
import json
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "hops"
POOL = OUT / "data" / "findings.jsonl"
HOPS = (4, 6, 8, 10)
FAMILIES = ("fam-a", "fam-b", "fam-c", "fam-d")
PER_KIND = 3  # hedged and firm studies per family
SEED = 2026
SEP = "\n---\n"
NEW = "/new"

FIRST = ("notes", "md", None)
MIDDLE = [
    ("table", "csv", "a CSV table with the columns id,finding and one row per study"),
    ("oneliners", "md", "one line per study of at most 15 words, each starting with the study's ID"),
    ("slides", "md", ("slide bullets for a short presentation, one bullet per study, each "
                      "starting with the study's ID")),
    ("email", "md", ("a short email to a colleague summarising what each study found, naming "
                     "each study by its ID")),
    ("plain", "md", ("a plain-language version for general readers, one short paragraph per "
                     "study, each starting with the study's ID")),
    ("takeaways", "md", "a list of key takeaways, one per study, each starting with the study's ID"),
    ("faq", "md", ("an FAQ with one question and answer per study, with the study's ID in each "
                   "question")),
    ("social", "md", ("one social media post per study, each under 280 characters and starting "
                      "with the study's ID")),
]
FINAL = ("briefing", "md", ("a briefing for a science policy adviser, one short paragraph per "
                            "study, each starting with the study's ID"))


def load_pool() -> list[dict]:
    return [json.loads(line) for line in POOL.read_text(encoding="utf-8").splitlines() if line]


def families(pool: list[dict]) -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    hedged = [r for r in pool if r["kind"] == "hedged"]
    firm = [r for r in pool if r["kind"] == "firm"]
    rng.shuffle(hedged)
    rng.shuffle(firm)
    out = {}
    for n, fam in enumerate(FAMILIES):
        picked = hedged[n * PER_KIND:(n + 1) * PER_KIND] + firm[n * PER_KIND:(n + 1) * PER_KIND]
        rng.shuffle(picked)
        out[fam] = [{"id": f"S{i:02d}", "kind": r["kind"], "finding": r["finding"],
                     "sentence_certainty": r["sentence_certainty"], "aspects": r["aspects"],
                     "pei_id": r["pei_id"]} for i, r in enumerate(picked, 1)]
    return out


def chain(family_index: int, hops: int) -> list[dict]:
    if not 3 <= hops <= len(MIDDLE) + 2:
        raise ValueError(f"hops must be 3..{len(MIDDLE) + 2}")
    shift = (2 * family_index) % len(MIDDLE)
    middle = (MIDDLE[shift:] + MIDDLE[:shift])[:hops - 2]
    kinds = [FIRST, *middle, FINAL]
    return [{"hop": i, "kind": kind, "file": f"hops/{i:02d}-{kind}.{ext}", "describe": desc}
            for i, (kind, ext, desc) in enumerate(kinds, 1)]


def steps(links: list[dict]) -> list[str]:
    out = [(f"Read every file in studies/ and write notes on each study's finding to "
            f"{links[0]['file']}. Start each study's entry with its ID (S01, S02, ...).")]
    for prev, link in itertools.pairwise(links):
        text = (f"Read {prev['file']} and write {link['file']}: {link['describe']}. Use only "
                f"{prev['file']} (do not open studies/ or any other file in hops/), and keep "
                f"each study's ID with its entry.")
        if link is links[-1]:
            text += " Then reply with the briefing."
        out.append(text)
    return out


def main() -> int:
    fams = families(load_pool())
    for sub in ("sandbox", "tasks"):
        if (OUT / sub).exists():
            shutil.rmtree(OUT / sub)
    (OUT / "tasks").mkdir(parents=True)
    count = 0
    for index, (fam, studies) in enumerate(fams.items()):
        for hops in HOPS:
            task = f"hops-{fam}-n{hops:02d}"
            folder = OUT / "sandbox" / task
            (folder / "studies").mkdir(parents=True)
            (folder / "hops").mkdir()
            (folder / "hops" / ".keep").write_text("", encoding="utf-8")
            for s in studies:
                (folder / "studies" / f"{s['id']}.md").write_text(
                    f"# Study {s['id']}\n\nReported finding: {s['finding']}\n",
                    encoding="utf-8", newline="\n")
            links = chain(index, hops)
            text = steps(links)
            (folder / "prompt-session.txt").write_text(SEP.join(text) + "\n", encoding="utf-8",
                                                       newline="\n")
            (folder / "prompt-relay.txt").write_text(SEP.join(
                part for n, step in enumerate(text) for part in ([NEW, step] if n else [step]))
                + "\n", encoding="utf-8", newline="\n")
            meta = {"id": task, "family": fam, "hops": hops,
                    "chain": [{k: v for k, v in link.items() if k != "describe"}
                              for link in links],
                    "studies": studies, "source": "Pei & Jurgens (EMNLP 2021), MIT"}
            (OUT / "tasks" / f"{task}.json").write_text(json.dumps(meta, indent=2) + "\n",
                                                        encoding="utf-8", newline="\n")
            count += 1
    print(f"built {count} hop tasks in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
