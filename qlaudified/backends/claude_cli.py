"""``claude -p --safe-mode --model <small> --output-format json`` (SID-3). Sprint 3.

--safe-mode loads no hooks, plugins or CLAUDE.md, so the nested call cannot recurse into qlaudified.
"""


class ClaudeCliBackend:
    name = "claude-cli"

    def __init__(self, model: str) -> None:
        self.model = model

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        raise NotImplementedError("Sprint 3: CFG-1, SID-3")
