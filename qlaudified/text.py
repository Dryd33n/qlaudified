"""Text helpers shared by claim extraction, BM25, Tier 1 and markers: sentences, tokens, numbers.

Numbers compare in the indexer's normalized form (``4200000 USD``, ``900 s``, ``2026-11-18``).
"""

import re
from collections.abc import Iterable

from qlaudified import indexer

_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "approx", "est", "co", "inc", "ltd", "corp", "mr", "ms", "mrs", "dr",
    "fig", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"')\]*_`]*\s+(?=[\"'(\[*_`]*[A-Z0-9$€£])")


def sentences(text: str) -> list[str]:
    """Split prose into sentences, keeping abbreviations (e.g., Co., Nov.) and decimals intact."""
    out: list[str] = []
    start = 0
    for m in _SENTENCE_BREAK.finditer(text):
        before = text[start:m.start()].rstrip(".!?\"')]*_`")
        last = before.rsplit(None, 1)[-1].lower() if before.split() else ""
        if last.rstrip(".") in _ABBREVIATIONS or re.fullmatch(r"[a-z]", last):
            continue
        out.append(text[start:m.start()].strip())
        start = m.end()
    out.append(text[start:].strip())
    return [s for s in out if s]


# References that look like numbers but aren't facts: file:line, locators, span markers.
_NOISE = re.compile(
    r"\[S\d+[^\]]*\]"  # our own markers
    r"|\b[\w./\\-]+\.\w+:\d+(?:-\d+)?\b"  # ledger/config.py:6
    r"|\bL\d+(?:-L?\d+)?\b"  # L3-L6
    r"|\bS\d+\b"  # S14
)


def clean(text: str) -> str:
    """Text for analysis: no markers, file:line references or backticks."""
    return _NOISE.sub(" ", text).replace("`", "")


def numbers(text: str) -> list[str]:
    """Normalized numbers and dates, as the indexer stores them in ``Span.numbers``."""
    return indexer.extract_numbers(text) + indexer.extract_dates(text)


def split_numbers(value: str) -> list[str]:
    return [v for v in (value or "").split("; ") if v]


def _is_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?|--\d{2}-\d{2}", value))


def number_match(a: str, b: str) -> bool:
    """Same amount (within 0.5%, units equal or one side unitless) or the same date.

    A less precise date matches a more precise one (``2026-11`` and ``2026-11-18``), and a date
    without a year matches the same day in any year (``--11-18`` and ``2026-11-18``)."""
    if _is_date(a) or _is_date(b):
        if not (_is_date(a) and _is_date(b)):
            return False
        if a.startswith("--") or b.startswith("--"):
            return len(a) in (7, 10) and len(b) in (7, 10) and a[-5:] == b[-5:]
        short, long = sorted((a, b), key=len)
        return long.startswith(short)
    va, _, ua = a.partition(" ")
    vb, _, ub = b.partition(" ")
    try:
        x, y = float(va), float(vb)
    except ValueError:
        return False
    if ua and ub and ua != ub:
        return False
    return abs(x - y) <= 0.005 * max(abs(x), abs(y)) or x == y


def same_kind(a: str, b: str) -> bool:
    """Both dates, or both amounts in the same unit (or both plain counts): a mismatch between
    them on the same topic means a different value."""
    if _is_date(a) or _is_date(b):
        return _is_date(a) and _is_date(b)
    return a.partition(" ")[2] == b.partition(" ")[2]


_STOPWORDS = """
a an the and or but if of to in on at by for with from as is are was were be been being it its this
that these those there here which who whom whose what when where why how than then so such not no
do does did done has have had having will would shall should can could may might must about into
over under per via i you he she we they them their our your my me us also just only very more most
some any each every all both either neither other another same own up down out off again further
once said says say according file files code read reads line lines note notes noted comment
comments docstring mention mentions mentioned state states stated show shows py md txt json toml
"""
STOPWORDS = set(_STOPWORDS.split())
_TOKEN = re.compile(r"[a-z][a-z0-9_]*|\d+(?:\.\d+)?")


def tokens(text: str) -> list[str]:
    """Lowercase content words, lightly stemmed (plural ``s`` dropped), stopwords removed."""
    out = []
    for word in _TOKEN.findall(text.lower()):
        # Identifiers also count by their parts: SYNC_INTERVAL_S matches "interval".
        parts = [word] + ([p for p in word.split("_") if p] if "_" in word else [])
        for t in parts:
            if t in STOPWORDS or len(t) < 2 and not t.isdigit():
                continue
            if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
                t = t[:-1]
            out.append(t)
    return out


def coverage(claim_tokens: Iterable[str], other: Iterable[str]) -> float:
    """Share of the claim's distinct content words found in ``other``."""
    want = set(claim_tokens)
    if not want:
        return 0.0
    return len(want & set(other)) / len(want)


def units(text: str) -> list[str]:
    """Passages small enough for a hedge to belong to the number next to it: the sentences of
    each line, split again at semicolons."""
    out = []
    for line in text.splitlines():
        if line.strip():
            out += [c.strip() for s in sentences(line.strip()) for c in s.split("; ") if c.strip()]
    return out
