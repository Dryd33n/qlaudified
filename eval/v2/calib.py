"""Calibration of each stated fact in an answer (study v2 primary outcome; methods critique, fix 3).

For every fact in a task's key the answer is scored as one of:

- **omitted**: the answer never states the fact's value;
- **kept**: stated with the source's certainty (hedged fact stated with a hedge, firm fact plainly);
- **inflated**: a hedged fact stated plainly (the drop the plugin is meant to prevent);
- **deflated**: a firm fact stated with a hedge (over-hedging, the plugin's possible harm).

Scope rules (frozen in docs/findings/protocol-v2.md):

1. Plugin text is removed first, in every condition: citation markers such as ``[F1]`` or
   ``[F2, qualifier: pending]`` and anything inside them. The scorer judges the prose a reader
   sees, so Medium gets no credit for a hedge that appears only in its own citations.
2. A fact's **scope** is the stretch of text that states its value: a table row, or the clause of
   a sentence around the value. When one sentence states several values, it is cut between them at
   the last clause break (". ", ``;``, ``,``, " and ", " but ", " while ", " whereas ",
   " compared with ", " vs ", " versus ", " from ", " up from ", " down from ", " against ") before
   the next value; when a colon introduces the next value ("...: 612. Forecast completions: 840"),
   the cut goes before that value's label instead, so the label stays with its value.
3. **Carried hedges** also count:
   - a heading line, or a table header row, that carries a hedge applies to everything under it;
   - a hedged lead-in before a colon ("All figures are preliminary: ...") applies to the rest of
     its sentence;
   - a sentence with a hedge but no figure of its own applies to every figure in the answer when it
     says "both", "these", "all", "the figures" or "the numbers"; otherwise to the figures in the
     sentence just before it, and only to those whose clause shares a topic word with it ("That Q3
     figure is still under review" reaches the Q3 figure, not the Q2 one).
4. A scope is **hedged** when it contains any cue from ``cues.py`` or a phrase from the fact's own
   source cue. One hedge is enough; its strength isn't compared with the source's, so "~" for
   "estimated", or "preliminary" for "estimated … preliminary", counts as kept.
"""

import itertools
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cues
import figures

_MARKERS = re.compile(r"\[(?:F\d+|S\d+)[^\]]*\]")
_BREAKS = re.compile(r"\.\s+|;|,|\s+(?:and|but|while|whereas|compared with|vs\.?|versus|from|up from|"
                     r"down from|against)\s+", re.IGNORECASE)
_COLLECTIVE = re.compile(r"\b(?:both|these|all|those|the (?:figures|numbers|values|estimates)|"
                         r"figures|numbers)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9$*(\"'])")


@dataclass
class FactScore:
    fact: str
    hedged_source: bool
    stated: bool
    hedged_answer: bool = False
    outcome: str = "omitted"  # omitted | kept | inflated | deflated
    scope: str = ""
    cues: list[str] = field(default_factory=list)


def strip_plugin_text(answer: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", _MARKERS.sub("", answer))


@dataclass
class Unit:
    """A table row, or a sentence of prose, with the hedge it inherits from above."""
    text: str
    inherited: list[str]
    is_table: bool


def _units(answer: str) -> list[Unit]:
    out: list[Unit] = []
    heading: list[str] = []
    table_header: list[str] = []
    for raw in answer.splitlines():
        line = raw.strip()
        if not line:
            table_header = []
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if not table_header and not figures.extract(line):
                table_header = cues.find(line)
                continue
            out.append(Unit(line, heading + table_header, True))
            continue
        table_header = []
        is_heading = line.startswith("#") or (line.endswith(":") and not figures.extract(line))
        if is_heading:
            heading = cues.find(line)
            continue
        for sentence in _SENTENCE.split(line):
            sentence = sentence.strip()
            if not sentence:
                continue
            # "All figures are preliminary: ..." heads the rest of its own sentence.
            lead, colon, rest = sentence.partition(":")
            lead_cues = cues.find(lead) if colon and rest.strip() and not figures.extract(lead) else []
            out.append(Unit(sentence, heading + lead_cues, False))
    return out


_GENERIC = {"figure", "figures", "number", "numbers", "value", "values", "that", "this", "these",
            "those", "still", "being", "will", "have", "with", "until", "after", "before", "only",
            "they", "them", "their", "there", "which", "while", "both", "also", "remain", "remains"}


def _topic(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9]+", text.lower())
    cue_words = {w for c in cues.find(text) for w in c.split()}
    return {w for w in words if (len(w) >= 4 or re.fullmatch(r"[qh]\d|fy\d+", w))
            and w not in _GENERIC and w not in cue_words}


def _segments(unit: Unit, figs: list[figures.Figure]) -> list[tuple[int, int]]:
    """Cut a sentence into one stretch per figure (rule 2); a table row is one stretch."""
    if unit.is_table or len(figs) < 2:
        return [(0, len(unit.text))] * len(figs)
    cuts = [0]
    for left, right in itertools.pairwise(figs):
        between = unit.text[left.end:right.start]
        breaks = list(_BREAKS.finditer(between))
        colon = between.rfind(":")
        if colon >= 0:
            # "...: 612. Forecast completions next year: 840": the next label belongs to the next
            # value, so cut before it, at the last break ahead of its colon.
            before = [m for m in breaks if m.start() < colon]
            cut = before[-1].start() if before else 0
        elif breaks:
            cut = breaks[-1].start()
        else:
            # No clause break ("about $3.7M (roughly 7.7%) to an unaudited $51.9M"): words before
            # a figure modify it, so cut right after the left figure, keeping a figure-free
            # parenthetical such as "(estimated)" with it.
            paren = re.match(r"\s*\([^()]*\)", between)
            cut = paren.end() if paren and not figures.extract(paren.group()) else 0
        cuts.append(left.end + cut)
    cuts.append(len(unit.text))
    return list(itertools.pairwise(cuts))


def _clause_cues(unit: Unit, figs: list, segments: list[tuple[int, int]], k: int) -> list[str]:
    """Hedges from figure-free ``;`` clauses of the same sentence ("...; the fare depends on the
    grant settlement"): they go to the segments sharing their topic, or, sharing none, to the
    figure just before them."""
    if unit.is_table or len(figs) < 1:
        return []
    out: list[str] = []
    start = 0
    for part in [*unit.text.split(";")]:
        end = start + len(part)
        found = cues.find(part) if not figures.extract(part) else []
        if found:
            topic = _topic(part)
            named = [j for j, (x, y) in enumerate(segments) if topic & _topic(unit.text[x:y])]
            before = [j for j, f in enumerate(figs) if f.end <= start]
            if k in named or (not named and before and before[-1] == k):
                out += found
        start = end + 1
    return out


def score_answer(answer: str, facts: list[dict]) -> list[FactScore]:
    text = strip_plugin_text(answer)
    units = _units(text)
    unit_figs = [figures.extract(u.text) for u in units]
    # Rule 3: a figure-free hedged sentence carries to the sentence before it, or to everything.
    carried_back: dict[int, list[tuple[set[str], list[str]]]] = {}
    global_cues: list[str] = []
    for i, (unit, figs) in enumerate(zip(units, unit_figs, strict=True)):
        if figs or unit.is_table:
            continue
        found = cues.find(unit.text)
        if not found:
            continue
        if _COLLECTIVE.search(unit.text):
            global_cues += found
        elif i > 0:
            carried_back.setdefault(i - 1, []).append((_topic(unit.text), found))

    scores = []
    for fact in facts:
        extra = [c for c in str(fact.get("cue", "")).split(",") if c.strip()]
        score = FactScore(fact["id"], bool(fact["hedged"]), stated=False)
        for i, (unit, figs) in enumerate(zip(units, unit_figs, strict=True)):
            hits = [k for k, f in enumerate(figs) if figures.matches(f, fact["value"], fact["unit"])]
            if not hits:
                continue
            segments = _segments(unit, figs)
            a, b = segments[hits[0]]
            scope = unit.text[a:b]
            carried = []
            for topic, found_after in carried_back.get(i, []):
                # A caveat that names a topic ("That Q3 figure...") goes to the segments sharing
                # it; one that names none goes to every figure in the sentence.
                named = [k for k, (x, y) in enumerate(segments) if topic & _topic(unit.text[x:y])]
                if not named or hits[0] in named:
                    carried += found_after
            carried += _clause_cues(unit, figs, segments, hits[0])
            found = cues.find(scope, extra) + unit.inherited + carried + global_cues
            score.stated, score.scope = True, scope.strip()
            score.hedged_answer = score.hedged_answer or bool(found)
            score.cues += found
        if score.stated:
            if score.hedged_source:
                score.outcome = "kept" if score.hedged_answer else "inflated"
            else:
                score.outcome = "deflated" if score.hedged_answer else "kept"
        scores.append(score)
    return scores


def complies(answer: str, fmt: str, style: str) -> bool | None:
    """Did the answer follow the prompt's format (and, for antihedge, carry no hedge at all)?

    ``None`` for natural prompts, which set no format."""
    if style == "natural":
        return None
    text = strip_plugin_text(answer).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if fmt == "table":
        ok = bool(lines) and all(ln.startswith("|") for ln in lines)
    else:  # slide: one short line
        ok = len(lines) == 1 and len(lines[0].split()) <= 30
    if style == "antihedge":
        ok = ok and not cues.hedged(text)
    return ok
