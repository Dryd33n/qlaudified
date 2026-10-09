"""Fact rows as a Read of each file would record them, for tests that need a ledger without hooks."""

from pathlib import Path

from qlaudified import capture
from qlaudified.store import Span


def spans_from_files(folder: Path, *files: str) -> list[Span]:
    out: list[Span] = []
    for name in files:
        content = (Path(folder) / name).read_text(encoding="utf-8")
        for origin, source, locator, text in capture._file_spans(name, content, 1):
            for fact in capture.facts_from_passage(origin, source, locator, text,
                                                   category="Internal Document"):
                fact.span_id = f"F{len(out) + 1}"
                out.append(fact)
    return out
