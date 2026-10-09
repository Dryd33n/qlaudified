"""Refeed: new ledger rows as compact factual lines, and where the ledger lives (RFD-1, RFD-2).

Line format: ``[F3 q3-update.md L3] Q3 revenue is estimated at $4.2M...; source says: estimated,
preliminary``. Plain facts only, never instructions. The study's placebo control (``refeed =
"placebo"``) sends the same lines with the qualifiers masked out: ``[F3 q3-update.md L3] Q3 revenue
is at $4.2M, based on figures.`` Rows are facts (a number, date or
qualifier), so every row is worth refeeding except search titles. Overflow points to
provenance.csv, which is always current (design revision 2).
"""

import re
from pathlib import Path

from qlaudified import lexicon
from qlaudified.store import Span

SNIPPET_CHARS = 90
_MARKUP = re.compile(r"^(?:[\s#>*+\-|]|//|/\*|\"\"\"|''')+|(?:\"\"\"|'''|\*/)\s*$")


def worth_injecting(span: Span) -> bool:
    """Search result titles are recorded but never refed: they rarely state a fact. Claude's own
    claims aren't refed either: it knows what it said."""
    return bool(span.numbers or span.qualifiers) and span.origin not in ("search-snippet", "claude")


def snippet(span: Span, limit: int = SNIPPET_CHARS) -> str:
    """The span's text on one line; a long span is cut to the line holding its first fact."""
    lines = [_MARKUP.sub("", ln).strip() for ln in span.text.splitlines()]
    lines = [ln for ln in lines if ln]
    text = " ".join(lines)
    if len(text) > limit:
        hedges = [w.lower() for w in span.qualifiers.split("; ") if w]
        first_number = next(iter(span.numbers.split("; ")), "").split(" ")[0]
        with_hedge = [ln for ln in lines if any(h in ln.lower() for h in hedges)]
        with_number = [ln for ln in lines if first_number and first_number in ln.replace(",", "")]
        text = next(iter(with_hedge + with_number), text)
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def mask_qualifiers(text: str, span: Span) -> str:
    """The text without the span's qualifiers or any lexicon hedge word (placebo refeed)."""
    words = {w for w in span.qualifiers.split("; ") if w}
    words |= {w for ws in lexicon.HEDGES.values() for w in ws}
    for word in sorted(words, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*[,;]?\s*\)|\[\s*\]", "", text)  # "(expected)" leaves "()"
    text = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s{2,}", " ", text))
    return re.sub(r"[,;:]+(?=[.!?]?$)", "", text.strip()).strip()


def format_line(span: Span, placebo: bool = False) -> str:
    if placebo:
        return f"[{span.span_id} {span.source} {span.locator}] {mask_qualifiers(snippet(span), span)}"
    line = f"[{span.span_id} {span.source} {span.locator}] {snippet(span)}"
    if span.qualifiers:
        line += "; source says: " + ", ".join(span.qualifiers.split("; "))
    return line


def _order(spans: list[Span]) -> list[Span]:
    """Qualified spans first, strongest hedge class first; then the rest in reading order."""
    def rank(span: Span) -> int:
        words = span.qualifiers.split("; ") if span.qualifiers else []
        classes = {cls for cls, ws in lexicon.HEDGES.items() for w in words if w in ws}
        top = lexicon.strongest(classes)
        return lexicon.STRENGTH_ORDER.index(top) if top in lexicon.STRENGTH_ORDER else (
            len(lexicon.STRENGTH_ORDER) if words else len(lexicon.STRENGTH_ORDER) + 1)
    return sorted(spans, key=rank)


def csv_hint(session_dir: Path, project: Path | None = None) -> str:
    """provenance.csv's path as Claude should see it: relative to the project when inside it."""
    path = Path(session_dir) / "provenance.csv"
    try:
        return path.relative_to(project).as_posix() if project else path.as_posix()
    except ValueError:
        return path.as_posix()


def session_line(csv_path: str) -> str:
    """The fact Claude gets at session start in Medium and High (RFD-1)."""
    return (f"qlaudified keeps this session's provenance ledger in {csv_path} (read-only): one row "
            "per critical fact read or stated so far (a figure, date or qualifier), with its "
            "source, the source's qualifiers and how it has been used. It updates after each "
            "tool call.")


def _overflow(rest: list[Span], csv_path: str = "") -> str:
    noun = "row" if len(rest) == 1 else "rows"
    if csv_path:
        return f"+{len(rest)} more provenance {noun} in {csv_path}"
    sources = list(dict.fromkeys(s.source for s in rest))
    named = ", ".join(sources[:3]) + (f" and {len(sources) - 3} more" if len(sources) > 3 else "")
    return f"+{len(rest)} more provenance {noun} from {named}"


def build_delta(spans: list[Span], budget_chars: int = 600, header: str = "",
                csv_path: str = "", placebo: bool = False) -> str:
    """Fit lines into the budget; overflow is a count plus the CSV's path (RFD-2)."""
    picked = _order([s for s in spans if worth_injecting(s)])
    lines = [header] if header else []
    used = len(header)
    for i, span in enumerate(picked):
        line = format_line(span, placebo)
        rest = picked[i + 1:]
        tail = len(_overflow(rest, csv_path)) + 1 if rest else 0
        if used + len(line) + 1 + tail > budget_chars:
            lines.append(_overflow(picked[i:], csv_path)[:budget_chars - used - 1]
                         if used < budget_chars else "")
            break
        lines.append(line)
        used += len(line) + 1
    body = [ln for ln in lines if ln]
    return "\n".join(body) if len(body) > (1 if header else 0) else ""
