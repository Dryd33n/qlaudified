"""No LLM: tier 3 is skipped and leftover claims are reported as ``unresolved``."""


class NoneBackend:
    name = "none"

    def __init__(self) -> None:
        self.last_usage: dict = {}

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        return None
