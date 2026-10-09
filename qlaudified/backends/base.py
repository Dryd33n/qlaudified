"""Backend interface: one JSON-schema-constrained completion per call, with usage logged."""

from typing import Protocol


class Backend(Protocol):
    name: str
    last_usage: dict  # cost, tokens and wall time of the last call, for usage.jsonl

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        """Return parsed JSON, or None when unavailable (callers report ``unresolved``)."""
        ...
