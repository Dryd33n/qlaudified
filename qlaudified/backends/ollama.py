"""Local Ollama HTTP API backend. Sprint 3 (on the cut list)."""


class OllamaBackend:
    name = "ollama"

    def __init__(self, model: str, url: str = "http://localhost:11434") -> None:
        self.model = model
        self.url = url

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        raise NotImplementedError("Sprint 3: CFG-1")
