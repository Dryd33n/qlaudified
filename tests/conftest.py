import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture
def repo() -> Path:
    return REPO


@pytest.fixture
def run_hook(repo, tmp_path):
    """Pipe a payload into hooks/run.py exactly as Claude Code would; returns the completed process."""

    def _run(event: str, payload: dict | str) -> subprocess.CompletedProcess:
        data = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            [sys.executable, str(repo / "hooks" / "run.py"), event],
            input=data.encode("utf-8"),
            capture_output=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
            timeout=30,
        )

    return _run
