"""Delta re-injection: new provenance rows as compact factual lines (INJ-1, INJ-2).

Line format: ``[S3 q3-update.md L3] Q3 revenue is estimated at $4.2M...; source says: estimated,
preliminary``. Plain facts only, never instructions. Only spans with a number, date or qualifier
are injected: those are what an answer can misstate, and Claude has just read the rest.
"""

import re

from qlaudified import lexicon
from qlaudified.store import Span

SNIPPET_CHARS = 90
_MARKUP = re.compile(r"^(?:[\s#>*+\-|]|//|/\*|\"\"\"|''')+|(?:\"\"\"|'''|\*/)\s*$")


def worth_injecting(span: Span) -> bool:
    """Search result titles are stored but never injected: they rarely state a fact."""
    return bool(span.numbers or span.qualifiers) and span.origin != "search-snippet"


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


def format_line(span: Span) -> str:
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


def _overflow(rest: list[Span]) -> str:
    sources = list(dict.fromkeys(s.source for s in rest))
    named = ", ".join(sources[:3]) + (f" and {len(sources) - 3} more" if len(sources) > 3 else "")
    noun = "span" if len(rest) == 1 else "spans"
    return f"+{len(rest)} more provenance {noun} from {named}"


def build_delta(spans: list[Span], budget_chars: int = 600, header: str = "") -> str:
    """Fit lines into the budget; summarize overflow as a count plus file path (INJ-2)."""
    picked = _order([s for s in spans if worth_injecting(s)])
    lines = [header] if header else []
    used = len(header)
    for i, span in enumerate(picked):
        line = format_line(span)
        rest = picked[i + 1:]
        tail = len(_overflow(rest)) + 1 if rest else 0
        if used + len(line) + 1 + tail > budget_chars:
            lines.append(_overflow(picked[i:])[:budget_chars - used - 1] if used < budget_chars else "")
            break
        lines.append(line)
        used += len(line) + 1
    body = [ln for ln in lines if ln]
    return "\n".join(body) if len(body) > (1 if header else 0) else ""
