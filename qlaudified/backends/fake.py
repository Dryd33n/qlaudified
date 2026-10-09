"""Canned-JSON backend for test layers 1-3, so model-dependent code stays deterministic and free."""


class FakeBackend:
    name = "fake"

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = list(responses or [])
        self.prompts: list[str] = []
        self.last_usage: dict = {}

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else None
