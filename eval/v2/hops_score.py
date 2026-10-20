"""Score hop-study runs: does a finding keep its source's certainty at every hop?

    py -3 eval/v2/hops_score.py --set dry [--estimator]

Each hop writes one artifact (``hops/NN-<kind>.<ext>``) and every artifact keeps each study's ID
(S01, S02, ...), so a study's text in an artifact is found by its ID: the stretch from a mention
of the ID to the next mention of a different ID (or the end of the file). A stretch with fewer
than three words counts as not stated ("S01 and S02 both..." gives S01 nothing; a known limit).

Per study and hop, against the source's human label (hops_select.py):

- hedged source: **kept** (the stretch carries a hedge cue), **inflated** (stated plainly) or
  **omitted**;
- firm source: **plain**, **deflated** (stated with a hedge: over-hedging) or **omitted**.

Reported:

1. Final hop by hop count and variant: hedged findings kept among those stated, firm findings
   deflated, omissions.
2. Survival by hop position: hedged findings kept at hop 1..N.
3. Loss by hop kind: of hedged findings still hedged in the artifact before, how many each kind
   of re-encoding (table, one-liners, slides, ...) states plainly. Hop kinds are rotated across
   families (hops_build.py) so position and kind are not confounded.
4. Re-reads (relay only, one transcript per hop): a hop after the first whose session opened
   studies/. Allowed, but it shortcuts the relay, so it is reported next to the result.

The lexicon is the study v2 cue list (cues.py) plus scientific hedges below. Hedge-word counts
are a weak measure of certainty (Pei & Jurgens report r = 0.55 with human ratings), so
``--estimator`` adds their sentence-level model (``pip install certainty-estimator``, ~500 MB
download on first use): the mean change in predicted certainty from source to final hop, where a
positive change means the finding was made to sound more certain.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import cues as _cues

TASKS = HERE / "hops" / "tasks"
RUNS = REPO / "eval" / "runs"

# Hedges common in scientific findings that cues.py (written for business documents) lacks.
# Left out on purpose: "associated", "linked", "correlated" (firm findings state associations
# plainly; Pei & Jurgens rate them as framing, not uncertainty).
SCIENCE = ["appeared", "appearing", "suggesting", "suggestive", "potential", "potentially",
           "perhaps", "maybe", "tend", "tends", "tended", "hypothesize", "hypothesise",
           "hypothesized", "speculate", "speculative", "uncertain", "unclear", "not clear",
           "some evidence", "in part", "partly", "partially", "relatively", "modest", "modestly",
           "generally", "often", "sometimes", "can help", "could help", "may help", "point to",
           "points to", "consistent with", "raises the possibility"]
_SCIENCE = re.compile("|".join(r"(?<!\w)" + re.escape(w) + r"(?!\w)"
                               for w in sorted(SCIENCE, key=len, reverse=True)), re.IGNORECASE)
_ID = re.compile(r"(?<![A-Za-z0-9])S0?(\d{1,2})(?!\d)")
MIN_WORDS = 3


def cues(text: str) -> list[str]:
    """Hedge cues in ``text``: study v2's list plus the scientific hedges above."""
    return _cues.find(text) + [m.group().lower() for m in _SCIENCE.finditer(text)]


def segments(text: str, ids: list[str]) -> dict[str, str]:
    """Each study's text in an artifact, keyed by ID (``S01``); absent IDs are left out."""
    wanted = {int(i[1:]): i for i in ids}
    marks = [(m.start(), wanted[int(m.group(1))]) for m in _ID.finditer(text)
             if int(m.group(1)) in wanted]
    found: dict[str, list[str]] = defaultdict(list)
    for n, (start, sid) in enumerate(marks):
        end = next((s for s, other in marks[n + 1:] if other != sid), len(text))
        if n and marks[n - 1][1] == sid:
            continue  # same study mentioned again inside its own stretch
        found[sid].append(text[start:end])
    return {sid: " ".join(parts) for sid, parts in found.items()}


def outcome(kind: str, stretch: str | None) -> str:
    if stretch is None or len(re.findall(r"[A-Za-z]{2,}", stretch)) < MIN_WORDS + 1:
        return "omitted"
    hedged = bool(cues(stretch))
    if kind == "hedged":
        return "kept" if hedged else "inflated"
    return "deflated" if hedged else "plain"


@dataclass
class Cell:
    study: str
    kind: str
    hop: int
    hop_kind: str
    outcome: str
    stretch: str


def score_run(folder: Path, task: dict) -> list[Cell]:
    ids = [s["id"] for s in task["studies"]]
    cells = []
    for step in task["chain"]:
        path = folder / step["file"]
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        segs = segments(text, ids)
        for s in task["studies"]:
            cells.append(Cell(s["id"], s["kind"], step["hop"], step["kind"],
                              outcome(s["kind"], segs.get(s["id"])), segs.get(s["id"], "")))
    return cells


WRITES = ("Write", "Edit", "MultiEdit", "NotebookEdit")
TARGETS = ("file_path", "path", "pattern", "command", "notebook_path")


def _opens_sources(line: str) -> bool:
    """A tool call in a transcript line that targets studies/ (not one whose text says "studies")."""
    try:
        content = (json.loads(line).get("message") or {}).get("content") or []
    except (json.JSONDecodeError, AttributeError):
        return False
    for use in content if isinstance(content, list) else []:
        if not isinstance(use, dict) or use.get("type") != "tool_use" or use.get("name") in WRITES:
            continue
        given = use.get("input") or {}
        if any("studies" in str(given.get(k, "")).replace("\\", "/") for k in TARGETS):
            return True
    return False


def rereads(folder: Path) -> int:
    """Hops after the first whose session opened studies/ (relay transcripts are per hop)."""
    return sum(any(_opens_sources(line) for line in path.read_text(encoding="utf-8").splitlines())
               for path in sorted(folder.glob("transcript-*.jsonl"))[1:])


def _rate(num: int, den: int) -> str:
    return f"{100 * num / den:.0f}% ({num}/{den})" if den else "n/a"


def report(rows: list[tuple[dict, dict, list[Cell], int]], estimator=None) -> str:
    out = []
    by = defaultdict(list)
    for result, task, cells, rr in rows:
        by[(task["hops"], result.get("variant", "?"))].append((task, cells, rr))
    out += ["## Final hop", "",
            ("| Hops | Variant | Runs | Hedged kept (of stated) | Firm deflated (of stated) "
             "| Omitted | Re-reads (relay) |"), "| --- | --- | --- | --- | --- | --- | --- |"]
    for (n, variant), items in sorted(by.items()):
        final = [c for task, cells, _ in items for c in cells if c.hop == task["hops"]]
        kept = sum(c.outcome == "kept" for c in final)
        infl = sum(c.outcome == "inflated" for c in final)
        defl = sum(c.outcome == "deflated" for c in final)
        plain = sum(c.outcome == "plain" for c in final)
        om = sum(c.outcome == "omitted" for c in final)
        rr = sum(r for _, _, r in items)
        out.append(f"| {n} | {variant} | {len(items)} | {_rate(kept, kept + infl)} | "
                   f"{_rate(defl, defl + plain)} | {_rate(om, len(final))} | {rr} |")
    out += ["", "## Survival by hop (hedged findings kept, of stated)", ""]
    for (n, variant), items in sorted(by.items()):
        cols = []
        for hop in range(1, n + 1):
            hc = [c for _, cells, _ in items for c in cells if c.hop == hop and c.kind == "hedged"]
            k = sum(c.outcome == "kept" for c in hc)
            cols.append(_rate(k, k + sum(c.outcome == "inflated" for c in hc)))
        out.append(f"- {n} hops, {variant}: " + " → ".join(cols))
    out += ["", "## Loss by hop kind (hedged before, stated plainly after)", "",
            "| Hop kind | At risk | Lost |", "| --- | --- | --- |"]
    risk, lost = defaultdict(int), defaultdict(int)
    for _, _, cells, _ in rows:
        prev = {}
        for c in sorted(cells, key=lambda c: (c.hop, c.study)):
            if c.kind == "hedged" and prev.get(c.study) == "kept" and c.outcome != "omitted":
                risk[c.hop_kind] += 1
                lost[c.hop_kind] += c.outcome == "inflated"
            if c.kind == "hedged":
                prev[c.study] = c.outcome
    for k in sorted(risk):
        out.append(f"| {k} | {risk[k]} | {_rate(lost[k], risk[k])} |")
    if estimator is not None:
        out += ["", "## Certainty change, source → final hop (certainty-estimator, 1-6)", "",
                "| Hops | Variant | Hedged: mean change | Firm: mean change |",
                "| --- | --- | --- | --- |"]
        for (n, variant), items in sorted(by.items()):
            deltas = defaultdict(list)
            for task, cells, _ in items:
                src = {s["id"]: s["finding"] for s in task["studies"]}
                final = [c for c in cells if c.hop == n and c.outcome != "omitted"]
                if not final:
                    continue
                pred = estimator([c.stretch for c in final] + [src[c.study] for c in final])
                half = len(final)
                for c, a, b in zip(final, pred[:half], pred[half:], strict=True):
                    deltas[c.kind].append(a - b)
            mean = {k: (f"{sum(v) / len(v):+.2f} (n={len(v)})" if v else "n/a")
                    for k, v in (("hedged", deltas["hedged"]), ("firm", deltas["firm"]))}
            out.append(f"| {n} | {variant} | {mean['hedged']} | {mean['firm']} |")
    return "\n".join(out) + "\n"


def load_estimator():
    from certainty_estimator.predict_certainty import CertaintyEstimator  # optional, eval only
    model = CertaintyEstimator("sentence-level")
    return lambda texts: [float(x) for x in model.predict(texts)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/v2/hops_score.py")
    parser.add_argument("--set", dest="run_set", default="dry")
    parser.add_argument("--estimator", action="store_true")
    args = parser.parse_args(argv)
    runs = RUNS / args.run_set / "hops"
    rows = []
    for folder in sorted(p for p in runs.glob("*") if (p / "result.json").exists()):
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        if result.get("returncode") != 0:
            continue
        task = json.loads((TASKS / f"{result['task']}.json").read_text(encoding="utf-8"))
        rows.append((result, task, score_run(folder, task), rereads(folder)))
    if not rows:
        print(f"no finished runs in {runs}")
        return 1
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # a Windows console is cp1252; the report has "→"
    print(report(rows, load_estimator() if args.estimator else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
