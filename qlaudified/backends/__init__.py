"""LLM backends (CFG-1): claude-cli (default), ollama, none, and fake for tests."""

from qlaudified.backends.base import Backend


def get_backend(name: str, model: str | None = None) -> Backend:
    if name == "claude-cli":
        from qlaudified.backends.claude_cli import ClaudeCliBackend

        return ClaudeCliBackend(model or "haiku")
    if name == "ollama":
        from qlaudified.backends.ollama import OllamaBackend

        return OllamaBackend(model or "")
    if name == "fake":
        from qlaudified.backends.fake import FakeBackend

        return FakeBackend()
    from qlaudified.backends.none import NoneBackend

    return NoneBackend()
