"""No LLM: tier 3 is skipped and leftover claims are reported as ``unresolved``."""


class NoneBackend:
    name = "none"

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        return None
