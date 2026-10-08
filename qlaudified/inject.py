"""Delta re-injection: new provenance rows as compact factual lines (INJ-1, INJ-2). Sprint 2.

Line format: ``[S14 notes/q3.md L22] Q3 revenue 4.2M USD; source says: estimated, preliminary``.
Plain facts only, never instructions or raw source text.
"""

from qlaudified.store import Span


def format_line(span: Span) -> str:
    raise NotImplementedError("Sprint 2: INJ-1")


def build_delta(spans: list[Span], budget_chars: int = 600) -> str:
    """Fit lines into the budget; summarize overflow as a count plus file path (INJ-2)."""
    raise NotImplementedError("Sprint 2: INJ-2")
