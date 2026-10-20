"""Select source findings for the hop study from Pei & Jurgens (EMNLP 2021).

    py -3 eval/v2/hops_select.py <path to a clone of Jiaxin-Pei/Certainty-in-Science-Communication>

Writes eval/v2/hops/data/findings.jsonl: the pool the hop tasks are built from (hops_build.py), so
building never needs the full dataset. The source data is MIT-licensed (data/LICENSE-pei-jurgens).

Every finding in the pool has both human labels: sentence-level certainty (1-6, mean of
annotators) and aspect-level certainty (Number, Extent, Probability, Condition, Suggestion,
Framing: NotPresent / Certain / Uncertain). Two kinds are kept:

- **hedged**: sentence-level <= 3.5, at least one of Probability, Number, Extent or Suggestion
  rated Uncertain, and at least one hedge cue the scorer's lexicon can see (``hops_score.cues``).
  The last rule is a limit of the standard-library scorer: findings whose uncertainty is only
  implied are left out. The certainty-estimator backend could score them; widening the pool is a
  later decision, written down before it is made.
- **firm**: sentence-level >= 5, no aspect rated Uncertain, and no lexicon cue, so a hedge in
  the answer is over-hedging, never a carried hedge.

Text is kept verbatim except for spaces before punctuation (``"evening ."`` -> ``"evening."``).
Findings with encoding damage, cut-off starts or endings ("ca.", "vs."), unbalanced brackets,
line-break hyphenation ("modifi- cations") or outside 70-260 characters are dropped.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hops_score

OUT = HERE / "hops" / "data" / "findings.jsonl"
HEDGE_ASPECTS = ("Probability", "Number", "Extent", "Suggestion")
_PRINTABLE = re.compile(r"^[A-Za-z0-9 .,;:'\"()%/\-+=<>&?!\[\]]+$")


def clean(text: str) -> str:
    return re.sub(r"\s+([.,;:%)])", r"\1", re.sub(r"\(\s+", "(", text.strip()))


def usable(text: str) -> bool:
    return (70 <= len(text) <= 260 and bool(_PRINTABLE.match(text)) and text.endswith(".")
            and (text[0].isupper() or text[0].isdigit())
            and not text.endswith(("ca.", "et al.", "e.g.", "i.e.", "vs.", "Fig."))
            and text.count("(") == text.count(")") and "aeu" not in text
            and "  " not in text  # abstract section labels: "Conclusions and Relevance  In ..."
            and not re.search(r"[a-z]- [a-z]", text))  # line-break hyphenation: "modifi- cations"


def kind(sentence: float, aspects: dict[str, str], text: str) -> str | None:
    has_cue = bool(hops_score.cues(text))
    if (sentence <= 3.5 and has_cue
            and any(aspects.get(a) == "Uncertain" for a in HEDGE_ASPECTS)):
        return "hedged"
    if sentence >= 5 and not has_cue and "Uncertain" not in aspects.values():
        return "firm"
    return None


def select(dataset: Path) -> list[dict]:
    folder = dataset / "data" / "annotated_data"
    sentence = {}
    for line in (folder / "sentence-level-certainty.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        sentence[rec["finding"]] = rec
    pool = []
    for line in (folder / "aspect-level-certainty.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        s = sentence.get(rec["finding"])
        text = clean(rec["finding"])
        if s is None or not usable(text):
            continue
        k = kind(s["sentence-level-certainty"], rec["aspect-level-certainty"], text)
        if k is None:
            continue
        pool.append({"pei_id": s["id"], "split": s["split"], "kind": k, "finding": text,
                     "sentence_certainty": s["sentence-level-certainty"],
                     "aspects": rec["aspect-level-certainty"],
                     "source_cues": hops_score.cues(text)})
    pool.sort(key=lambda r: r["pei_id"])
    return pool


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2])
        return 2
    pool = select(Path(argv[0]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r) + "\n" for r in pool), encoding="utf-8", newline="\n")
    hedged = sum(r["kind"] == "hedged" for r in pool)
    print(f"wrote {len(pool)} findings ({hedged} hedged, {len(pool) - hedged} firm) to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
