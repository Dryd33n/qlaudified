"""Inline answer markers such as ``[S3]`` and ``[S3, qualifier: estimated]`` (REP-1).

Claude Code holds each streamed batch until MessageDisplay returns, so markers come from fast
deterministic matching: sentences that state a number or date are run through Tier 1 against the
spans that hold numbers. Full verdicts (unsupported, contradicted) wait for the Stop report.
Code blocks, tables and headings are left alone; a fence can span batches, so its state is passed in.
"""

import re

from qlaudified import text
from qlaudified.store import Span
from qlaudified.verify import tier1

_FENCE = re.compile(r"^\s*(```|~~~)")
_HAS_MARKER = re.compile(r"\[S\d+")
_END = re.compile(r"[.!?:;,]*[\"')\]*_`]*\s*$")


def _marker(sentence: str, spans: list[Span], lex) -> str:
    cleaned = text.clean(sentence)
    nums = text.numbers(cleaned)
    if not nums or _HAS_MARKER.search(sentence):
        return ""
    candidates = [s for s in spans
                  if any(text.number_match(n, m) for n in nums for m in text.split_numbers(s.numbers))]
    if not candidates:
        return ""
    result = tier1.check(sentence, candidates, lex)
    if not result or result["verdict"] not in ("supported", "partial", "qualifier-dropped"):
        return ""
    ids = ", ".join(result["span_ids"][:2])
    if result["verdict"] == "qualifier-dropped":
        return f" [{ids}, qualifier: {', '.join(result['dropped_qualifiers'][:2])}]"
    return f" [{ids}]"


def _mark_line(line: str, spans: list[Span], lex) -> str:
    out, pos = [], 0
    for sentence in text.sentences(line):
        start = line.find(sentence, pos)
        if start < 0:
            continue
        end = start + len(sentence)
        marker = _marker(sentence, spans, lex)
        if marker:
            tail = _END.search(sentence)  # always matches: every part is optional
            cut = start + (tail.start() if tail else len(sentence))
            out.append(line[pos:cut] + marker + line[cut:end])
        else:
            out.append(line[pos:end])
        pos = end
    out.append(line[pos:])
    return "".join(out)


def add_markers(delta: str, spans: list[Span], lex=None, in_fence: bool = False) -> tuple[str, bool]:
    """Return the marked text and whether a code fence is still open at its end."""
    lines = delta.split("\n")
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        s = line.strip()
        if in_fence or not s or s.startswith(("#", "|")) or line.startswith(("    ", "\t")):
            continue
        lines[i] = _mark_line(line, spans, lex)
    return "\n".join(lines), in_fence
