"""Store locations under ``<project>/.claude/.qlaudified/``."""

import os
from pathlib import Path

from qlaudified import NAME


def project_dir(payload: dict | None = None) -> Path:
    """Project root: ``CLAUDE_PROJECT_DIR``, else the payload's ``cwd``, else the process cwd."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or (payload or {}).get("cwd") or os.getcwd()
    return Path(root)


def store_root(payload: dict | None = None) -> Path:
    return project_dir(payload) / ".claude" / f".{NAME}"


def session_dir(session_id: str, payload: dict | None = None) -> Path:
    return store_root(payload) / "sessions" / session_id
