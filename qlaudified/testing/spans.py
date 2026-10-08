"""Spans as a Read of each file would store them, for tests that need a session without hooks."""

import hashlib
from pathlib import Path

from qlaudified import capture, indexer
from qlaudified.store import Span


def spans_from_files(folder: Path, *files: str) -> list[Span]:
    out: list[Span] = []
    for name in files:
        content = (Path(folder) / name).read_text(encoding="utf-8")
        for origin, source, locator, text in capture._file_spans(name, content, 1):
            hedges = indexer.find_hedges(text)
            out.append(Span(
                f"S{len(out) + 1}", origin, source, locator, text,
                numbers="; ".join(indexer.extract_numbers(text) + indexer.extract_dates(text)),
                qualifiers="; ".join(w for ws in hedges.values() for w in ws),
                hash=hashlib.sha256(text.encode()).hexdigest()[:16]))
    return out
