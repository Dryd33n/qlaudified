"""Carry critical facts across sessions (RFD-5).

The ledger is per session, so a new session starts empty. Work is often handed over between
sessions: one session reads the sources, a later one is given the report built from them and
asked to turn it into a slide. Without the plugin, that is where hedges are lost (README, "Where
hedges get lost"). So when the user's prompt or a file Claude reads names something an earlier
session in this project recorded, those earlier rows go back to Claude as plain factual lines, in
the RFD-2 line format, within ``carry_budget_chars``, each row at most once per session.

Rows are carried as the ledger holds them, hedged or firm, like every other refeed: a firm row in
its source's own wording is how Claude can tell which findings the sources stated plainly. (The
first version carried only rows with qualifiers; Claude then knew which sources hedged but not
which did not, and covered firm findings with a blanket caveat. eval/README.md, Oct 21 result.)

Matching is lexical: a row matches when it shares at least two distinctive words with the new
text, a word being distinctive when at most half of the earlier rows contain it. Rows are picked
greedily by the new text's words they cover that earlier picks did not, so a report naming six
interventions gets a line per intervention before a second line for any one; among equal picks,
rows with qualifiers go first.
"""

import json
import math
import re
import sqlite3
from pathlib import Path

from qlaudified import inject, paths
from qlaudified.records import asdict
from qlaudified.store import Span, Store

HEADER = "Facts recorded in earlier sessions of this project that this matches (qlaudified):"
CARRIED = "carried.json"  # per session: span keys already sent, so each goes once
MAX_SESSIONS = 20  # the most recent earlier sessions, by ledger time
MIN_SHARED = 2
SOURCE_CHARS = 48  # longer source labels (whole shell commands) are cut in carried lines
_WORD = re.compile(r"[A-Za-z][A-Za-z-]{2,}")
_STOP = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "these", "those", "was", "were", "are",
    "has", "have", "had", "been", "being", "into", "than", "then", "them", "they", "their",
    "there", "which", "while", "what", "when", "where", "who", "whom", "will", "would", "could",
    "should", "may", "might", "can", "not", "but", "all", "any", "each", "per", "our", "out",
    "over", "under", "about", "after", "before", "also", "only", "very", "more", "most", "less",
    "much", "such", "some", "other", "study", "studies", "trial", "trials", "report", "reports",
    "result", "results", "found", "showed", "shows", "compared", "group", "groups", "usual",
    "care", "participants", "patients", "effect", "effects", "reduced", "reduce", "reduces",
    "reduction", "increased", "increase", "lower", "higher", "percent", "across",
})


def words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)} - _STOP


def earlier_sessions(session_id: str, payload: dict | None = None) -> list[Path]:
    """Other sessions' ledgers in this project, most recent first."""
    root = paths.store_root(payload) / "sessions"
    if not root.is_dir():
        return []
    current = paths.safe_name(session_id)
    found = [p for p in root.iterdir()
             if p.is_dir() and p.name != current and (p / "index.sqlite").exists()]
    found.sort(key=lambda p: (p / "index.sqlite").stat().st_mtime, reverse=True)
    return found[:MAX_SESSIONS]


def earlier_facts(session_id: str, payload: dict | None = None) -> list[Span]:
    """Critical facts earlier sessions read from a source, hedged or firm (RFD-2's filter; not
    Claude's own claims or the user's prompts)."""
    facts: list[Span] = []
    seen: set[tuple[str, str, str]] = set()
    for folder in earlier_sessions(session_id, payload):
        store = Store(folder)
        try:
            spans = store.spans()
        except (sqlite3.Error, OSError):
            continue  # a damaged or locked ledger: skip it, never fail the hook
        finally:
            store.close()
        for span in spans:
            key = (span.source, span.locator, span.text)
            if (span.origin not in ("claude", "user-prompt") and inject.worth_injecting(span)
                    and key not in seen):
                seen.add(key)
                facts.append(span)
    return facts


def pick(facts: list[Span], text: str, budget_chars: int) -> list[Span]:
    """Facts that match ``text``, greedily by new words covered, within the budget."""
    query = words(text)
    if not query or not facts or budget_chars <= 0:
        return []
    bags = [words(f.text) for f in facts]
    df: dict[str, int] = {}
    for bag in bags:
        for w in bag:
            df[w] = df.get(w, 0) + 1
    limit = len(facts) / 2

    def distinctive(bag: set[str]) -> set[str]:
        return {w for w in bag & query if df[w] <= limit}

    def weight(ws: set[str]) -> float:
        return sum(math.log(1 + len(facts) / df[w]) for w in ws)

    candidates = [(f, distinctive(b)) for f, b in zip(facts, bags, strict=True)]
    candidates = [(f, ws) for f, ws in candidates if len(ws) >= MIN_SHARED]
    order = {f.span_id + f.source: i for i, f in enumerate(inject._order([f for f, _ in candidates]))}
    picked: list[Span] = []
    covered: set[str] = set()
    used = len(HEADER)
    while candidates:
        best = max(candidates, key=lambda c: (weight(c[1] - covered), weight(c[1]),
                                              -order[c[0].span_id + c[0].source]))
        candidates.remove(best)
        line = len(line_for(best[0])) + 1
        if used + line > budget_chars:
            continue  # a shorter line may still fit
        picked.append(best[0])
        covered |= best[1]
        used += line
    return picked


def line_for(span: Span, placebo: bool = False) -> str:
    """The RFD-2 line, with a long source label cut: a fact read through a shell command has the
    whole command as its source, which would use most of the budget. The CSV keeps it in full."""
    if len(span.source) <= SOURCE_CHARS:
        return inject.format_line(span, placebo)
    short = Span(**{**asdict(span), "source": span.source[:SOURCE_CHARS - 1].rstrip() + "…"})
    return inject.format_line(short, placebo)


def _key(span: Span) -> str:
    return f"{span.source}#{span.locator}#{span.text[:80]}"


def carry(session_id: str, text: str, budget_chars: int, payload: dict | None = None,
          placebo: bool = False) -> str:
    """Lines for earlier sessions' facts that match ``text`` and were not sent this session."""
    if budget_chars <= 0 or not text.strip():
        return ""
    folder = paths.session_dir(session_id, payload)
    sent_path = folder / CARRIED
    try:
        sent = set(json.loads(sent_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        sent = set()
    facts = [f for f in earlier_facts(session_id, payload) if _key(f) not in sent]
    picked = pick(facts, text, budget_chars)
    if not picked:
        return ""
    folder.mkdir(parents=True, exist_ok=True)
    sent_path.write_text(json.dumps(sorted(sent | {_key(f) for f in picked})), encoding="utf-8")
    return "\n".join([HEADER, *(line_for(f, placebo) for f in picked)])


def session_note(session_id: str, payload: dict | None = None) -> str:
    """The SessionStart fact: earlier ledgers exist, and how many critical facts they hold."""
    facts = earlier_facts(session_id, payload)
    if not facts:
        return ""
    sessions = len(earlier_sessions(session_id, payload))
    qualified = sum(1 for f in facts if f.qualifiers)
    return (f"Earlier sessions in this project ({sessions}) recorded {len(facts)} critical facts "
            f"from sources ({qualified} with qualifiers); qlaudified returns the ones that the "
            "prompt or a file read in this session matches.")
