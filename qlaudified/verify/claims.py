"""Rule-based claim extraction from prose, list items and table cells; code blocks skipped (VER-1).

A claim is a sentence, split further at clause joints (``;``, ``, which``, ``, and``, ...) so a
compound like "syncs every 900 seconds, which is 15 minutes" becomes two checkable claims. Table
rows count as one claim each, with the header row dropped. Headings are skipped.
"""

import re

from qlaudified import indexer, text

_FENCE = re.compile(r"^\s*(```|~~~)")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")
# Clause joints. "which" stays with its clause ("which is 15 minutes"); the others are dropped.
_JOINT = re.compile(r";\s+|,\s+(?=which\s)|,\s+(?:and|but|while|whereas|although|though)\s+")
_AND = re.compile(r"\s+and\s+")
_COMPARISON = re.compile(
    r"\b(?:more|less|fewer|greater|higher|lower|larger|smaller|faster|slower|earlier|later|than"
    r"|increased?|decreased?|grew|rose|fell|doubled|halved|exceeds?|outperforms?)\b",
    re.IGNORECASE,
)
# A capitalized word past the first, not a short acronym (AI, URLs, IDs); or inline code.
_ENTITY = re.compile(r"(?<!^)(?<![.!?]\s)\b(?![A-Z]{1,4}s?\b)[A-Z][a-zA-Z]+\b|`[^`]+`")
# The assistant talking about itself or to the user, not about a source.
_PERSONAL = re.compile(
    r"(?-i:\bI(?:'m|'ve|'ll|'d)?\b)|\b(?:me|my|you|your|you're|you'll|we|we've|we'll|let's|let me)\b"
    r"|^(?:here (?:is|are)|if you)\b",
    re.IGNORECASE,
)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_EMPHASIS = re.compile(r"\*\*|__")
MIN_WORDS = 3


def _paragraphs(answer: str) -> list[str]:
    """Prose paragraphs, list items and table rows, in order; code and headings dropped."""
    out: list[str] = []
    para: list[str] = []
    lines = answer.splitlines()
    in_fence = False

    def flush() -> None:
        if para:
            out.append(" ".join(para))
            para.clear()

    for i, line in enumerate(lines):
        if _FENCE.match(line):
            flush()
            in_fence = not in_fence
            continue
        s = line.strip()
        indented_code = line.startswith(("    ", "\t")) and not para and not _BULLET.match(line)
        if in_fence or not s or s.startswith("#") or indented_code:
            flush()
            continue
        if s.startswith("|"):
            flush()
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if _TABLE_SEP.match(s) or _TABLE_SEP.match(nxt):
                continue  # separator, or the header row above it
            out.append(", ".join(c.strip() for c in s.strip("|").split("|") if c.strip()))
            continue
        s = s.lstrip("> ").strip()
        if _BULLET.match(s):
            flush()
            s = _BULLET.sub("", s)
            if _LINK.fullmatch(s):
                continue  # a bare link in a source list
        para.append(_EMPHASIS.sub("", _LINK.sub(r"\1", s)))
    flush()
    return out


def _split_clauses(sentence: str) -> list[str]:
    parts = [p for p in _JOINT.split(sentence) if p and p.strip()]
    out = []
    for part in parts:
        # A bare "and" splits only between two clauses that each state a number or date.
        pieces = _AND.split(part)
        if len(pieces) == 2 and all(text.numbers(text.clean(p)) for p in pieces) \
                and all(len(p.split()) >= MIN_WORDS for p in pieces):
            out += pieces
        else:
            out.append(part)
    return [p.strip().rstrip(",;") for p in out]


def extract_claims(answer: str) -> list[str]:
    return [claim for claim, _ in claims_in_context(answer)]


def claims_in_context(answer: str) -> list[tuple[str, str]]:
    """(claim, its whole sentence). A hedge anywhere in the sentence still qualifies each clause:
    "$12 per seat, but that is subject to change" keeps its qualifier after the split."""
    out = []
    for para in _paragraphs(answer):
        for sentence in text.sentences(para):
            out += [(c, sentence) for c in _split_clauses(sentence)
                    if len(c.split()) >= MIN_WORDS and not _lead_in(c)]
    return out


def _lead_in(claim: str) -> bool:
    """A short label that introduces a list or quote ("Whether to trust them:")."""
    return claim.rstrip().endswith(":") and len(claim.split()) <= 6


def criticality(claim: str, lexicon: dict[str, list[str]] | None = None) -> float:
    """1.0 number or date, 0.8 qualifier, 0.7 comparison, 0.5 named entity, else 0.3.

    0.0 for the assistant talking about itself or to the user: there's no source to check."""
    t = text.clean(claim)
    if _PERSONAL.search(t):
        return 0.0
    if text.numbers(t):
        return 1.0
    if indexer.find_hedges(t, lexicon):
        return 0.8
    if _COMPARISON.search(t):
        return 0.7
    if _ENTITY.search(claim.strip()):
        return 0.5
    return 0.3


def is_critical(claim: str, threshold: float = 0.5,
                lexicon: dict[str, list[str]] | None = None) -> bool:
    """Number, date, named entity, comparison or qualifier (at the default threshold)."""
    return criticality(claim, lexicon) >= threshold
