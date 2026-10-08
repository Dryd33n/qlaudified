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

    def _run(event: str, payload: dict | str, project: Path | None = None) -> subprocess.CompletedProcess:
        data = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            [sys.executable, str(repo / "hooks" / "run.py"), event],
            input=data.encode("utf-8"),
            capture_output=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(project or tmp_path)},
            timeout=30,
            check=False,
        )

    return _run
