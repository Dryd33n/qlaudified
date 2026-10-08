"""Span indexer: numbers, dates, units, entities and hedge words for a passage (CAP-2). Sprint 1."""


def normalize_number(text: str) -> float | None:
    """'$4.2M' and '4.2 million USD' -> 4200000.0."""
    raise NotImplementedError("Sprint 1: CAP-2")


def extract_numbers(text: str) -> list[str]:
    raise NotImplementedError("Sprint 1: CAP-2")


def extract_dates(text: str) -> list[str]:
    raise NotImplementedError("Sprint 1: CAP-2")


def find_hedges(text: str, lexicon: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Hedge class -> matched words."""
    raise NotImplementedError("Sprint 1: CAP-2")
