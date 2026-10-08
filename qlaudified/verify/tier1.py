"""Deterministic tier: number/date/unit match, hedge diff, fuzzy overlap (VER-2, VER-3).

Spans are compared line by line (sentence by sentence for long lines), so a hedge counts only for
the number it sits next to: in a code block, ``SYNC_INTERVAL_S = 900`` is unhedged even when the
comment above it says "roughly 15 minutes".

A qualifier is dropped when the matched passage's strongest hedge class is missing from the claim
(lexicon.STRENGTH_ORDER). When several passages state the same number, one that the claim fully
covers wins, so restating an unhedged value never counts as dropping someone else's hedge.
"""

from dataclasses import dataclass, field

from qlaudified import indexer, lexicon, text
from qlaudified.store import Span

MIN_SPAN_OVERLAP = 0.25  # a number match also needs some shared words, unless the claim is tiny
SUPPORTED_OVERLAP = 0.8  # claims without numbers: share of content words found in one passage
PARTIAL_OVERLAP = 0.5
CONTRADICTION_OVERLAP = 0.5


@dataclass
class Unit:
    span: Span
    text: str
    numbers: list[str]
    hedges: dict[str, list[str]]
    tokens: set[str] = field(default_factory=set)


_cache: dict[tuple[str, str, int], list[Unit]] = {}


def units_of(span: Span, lex: dict[str, list[str]] | None = None) -> list[Unit]:
    key = (span.span_id, span.hash, id(lex))
    if key not in _cache:
        _cache[key] = [
            Unit(span, u, text.numbers(text.clean(u)), indexer.find_hedges(u, lex),
                 set(text.tokens(text.clean(u))))
            for u in text.units(span.text)
        ]
    return _cache[key]


def missing_qualifiers(source: dict[str, list[str]], claim_classes: set[str]) -> list[str]:
    """Hedge words the claim dropped: empty unless the source's strongest class is absent."""
    strongest = lexicon.strongest(set(source))
    if strongest is None or strongest in claim_classes:
        return []
    order = [c for c in lexicon.STRENGTH_ORDER if c in source] + sorted(
        c for c in source if c not in lexicon.STRENGTH_ORDER)
    return [w for c in order if c not in claim_classes for w in source[c]]


def _verdict(verdict: str, units: list[Unit], confidence: float,
             dropped: list[str] | None = None) -> dict:
    return {
        "verdict": verdict,
        "span_ids": list(dict.fromkeys(u.span.span_id for u in units)),
        "dropped_qualifiers": list(dict.fromkeys(dropped or [])),
        "decided_by": "deterministic",
        "confidence": round(confidence, 2),
    }


def check(claim: str, spans: list[Span], lex: dict[str, list[str]] | None = None,
          context: str | None = None) -> dict | None:
    """Verdict dict if decided, else None (moves to the next tier).

    ``context`` is the claim's whole sentence: its hedges count for the claim too."""
    cleaned = text.clean(claim)
    claim_numbers = text.numbers(cleaned)
    claim_classes = set(indexer.find_hedges(text.clean(context or claim), lex))
    claim_tokens = text.tokens(cleaned)
    units = [u for s in spans for u in units_of(s, lex)]
    if not units:
        return None
    if claim_numbers:
        return _check_numbers(claim_numbers, claim_classes, claim_tokens, spans, units, lex)
    return _check_words(claim_classes, claim_tokens, units)


def _check_numbers(claim_numbers, claim_classes, claim_tokens, spans, units, lex) -> dict | None:
    tiny = len(set(claim_tokens)) <= 2
    on_topic = {
        s.span_id for s in spans
        if tiny or text.coverage(claim_tokens, text.tokens(text.clean(s.text))) >= MIN_SPAN_OVERLAP
    }
    matches = {
        n: [u for u in units if u.span.span_id in on_topic
            and any(text.number_match(n, m) for m in u.numbers)]
        for n in claim_numbers
    }
    covered = [n for n in claim_numbers if matches[n]]
    if not covered:
        for u in units:
            overlap = text.coverage(claim_tokens, u.tokens)
            if overlap >= CONTRADICTION_OVERLAP and any(
                text.same_kind(n, m) and not text.number_match(n, m)
                for n in claim_numbers for m in u.numbers
            ):
                return _verdict("contradicted", [u], 0.5 + 0.4 * overlap)
        return None

    used: list[Unit] = []
    dropped: list[str] = []
    for n in covered:
        options = sorted(matches[n], key=lambda u: -text.coverage(claim_tokens, u.tokens))
        clean = next((u for u in options if not missing_qualifiers(u.hedges, claim_classes)), None)
        if clean is not None:
            used.append(clean)
            continue
        used.append(options[0])
        dropped += missing_qualifiers(options[0].hedges, claim_classes)
    if dropped:
        return _verdict("qualifier-dropped", used, 0.8, dropped)
    # The passage that matched one number states a different value for another: contradicted.
    for n in claim_numbers:
        if n in covered:
            continue
        for u in used:
            if any(text.same_kind(n, m) and not text.number_match(n, m) for m in u.numbers):
                return _verdict("contradicted", [u], 0.75)
    if len(covered) < len(claim_numbers):
        return _verdict("partial", used, 0.4 + 0.4 * len(covered) / len(claim_numbers))
    return _verdict("supported", used, 0.9)


def _check_words(claim_classes, claim_tokens, units) -> dict | None:
    if len(set(claim_tokens)) < 2:
        return None
    best = max(units, key=lambda u: text.coverage(claim_tokens, u.tokens))
    overlap = text.coverage(claim_tokens, best.tokens)
    if overlap >= SUPPORTED_OVERLAP:
        dropped = missing_qualifiers(best.hedges, claim_classes)
        if dropped:
            return _verdict("qualifier-dropped", [best], 0.6, dropped)
        return _verdict("supported", [best], overlap * 0.8)
    if overlap >= PARTIAL_OVERLAP:
        return _verdict("partial", [best], overlap * 0.8)
    return None
