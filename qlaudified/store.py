"""Session store: SQLite (WAL, busy timeout) is the source of truth; provenance.csv is an export.

Layout per session: index.sqlite, provenance.csv, raw/<hash>.txt, reports/turn-<n>.{md,json},
usage.jsonl. Sprint 1.
"""

from dataclasses import dataclass


@dataclass
class Span:
    span_id: str  # "S14"
    origin: str  # local-doc | code | command-output | web-raw | web-summary | search-snippet | user-prompt
    source: str  # path or URL
    locator: str  # "L22-L24" or "p7"
    text: str
    numbers: str = ""
    qualifiers: str = ""
    derived_from: str | None = None
    agent_id: str = "main"
    turn: str | None = None  # prompt_id
    ts: str = ""
    hash: str = ""


@dataclass
class Claim:
    claim_id: str
    turn: str
    text: str
    span_ids: list[str]
    # supported | partial | qualifier-dropped | contradicted | unsupported | inference | unresolved
    verdict: str
    dropped_qualifiers: list[str]
    decided_by: str  # deterministic | nli | llm
    confidence: float
    critical: bool


class Store:
    def __init__(self, session_dir) -> None:
        self.session_dir = session_dir

    def add_span(self, span: Span) -> str:
        raise NotImplementedError("Sprint 1: CAP-1")

    def spans_since(self, marker: str | None) -> list[Span]:
        raise NotImplementedError("Sprint 2: INJ-1")

    def add_claims(self, claims: list[Claim]) -> None:
        raise NotImplementedError("Sprint 2: VER-2")

    def export_csv(self) -> None:
        raise NotImplementedError("Sprint 1")
