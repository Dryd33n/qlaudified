import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from qlaudified.testing.sim import placeholders, substitute

FIXTURES = REPO / "tests" / "fixtures" / "payloads"


@pytest.fixture
def repo() -> Path:
    return REPO


@pytest.fixture
def sandbox(tmp_path) -> Path:
    """The project folder that recorded ``<SANDBOX>`` paths resolve to."""
    path = tmp_path / "sandbox"
    path.mkdir()
    return path


@pytest.fixture
def payload(tmp_path, sandbox):
    """Load tests/fixtures/payloads/<name>.json with placeholders swapped for this test's folders."""

    def _load(name: str) -> dict:
        data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        return substitute(data, placeholders(tmp_path))

    return _load


@pytest.fixture
def run_hook(repo, tmp_path):
    """Pipe a payload into hooks/run.py exactly as Claude Code would; returns the completed process."""

    def _run(event: str, payload: dict | str, project: Path | None = None,
             offline: bool = True) -> subprocess.CompletedProcess:
        data = payload if isinstance(payload, str) else json.dumps(payload)
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project or tmp_path)}
        if not offline:
            env.pop("QLAUDIFIED_OFFLINE", None)
        return subprocess.run(
            [sys.executable, str(repo / "hooks" / "run.py"), event],
            input=data.encode("utf-8"),
            capture_output=True,
            env=env,
            timeout=30,
            check=False,
        )

    return _run


REAL_CACHE = os.environ.get("QLAUDIFIED_CACHE") or str(Path.home() / ".cache" / "qlaudified")


@pytest.fixture(autouse=True)
def no_nli_model_and_offline(tmp_path_factory, monkeypatch):
    """Tests run without the NLI model, as CI does (test_tiers.py opts back in), and offline: no
    background jobs and no LLM backend, so no test can make a real model call by accident."""
    monkeypatch.setenv("QLAUDIFIED_CACHE", str(tmp_path_factory.mktemp("cache")))
    monkeypatch.setenv("QLAUDIFIED_OFFLINE", "1")
