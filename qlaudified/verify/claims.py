"""Rule-based claim extraction from prose, list items and table cells; code blocks skipped (VER-1).

Sprint 2.
"""


def extract_claims(answer: str) -> list[str]:
    raise NotImplementedError("Sprint 2: VER-1")


def is_critical(claim: str) -> bool:
    """Number, date, named entity, comparison or qualifier."""
    raise NotImplementedError("Sprint 2: VER-1")
