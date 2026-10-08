"""High-mode in-loop sidecar on flagged sentences only (SID-1, SID-2). Sprint 4."""


def flag_sentences(text: str) -> list[str]:
    """Sentences with numbers, dates, hedges or entities (SID-1)."""
    raise NotImplementedError("Sprint 4: SID-1")


def classify(sentences: list[str], backend) -> list[dict]:
    """Criticality and extra qualifiers per flagged sentence (SID-2)."""
    raise NotImplementedError("Sprint 4: SID-2")
