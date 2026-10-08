"""Store locations under ``<project>/.claude/.qlaudified/`` and path normalization."""

import os
import re
import sys
from pathlib import Path

from qlaudified import NAME

STORE_REL = f".claude/.{NAME}"


def project_dir(payload: dict | None = None) -> Path:
    """Project root: ``CLAUDE_PROJECT_DIR``, else the payload's ``cwd``, else the process cwd."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or (payload or {}).get("cwd") or os.getcwd()
    return Path(long_path(root))


def store_root(payload: dict | None = None) -> Path:
    return project_dir(payload) / ".claude" / f".{NAME}"


def ensure_gitignore(root: Path) -> None:
    """Raw copies can hold secrets, so the whole store is ignored by default. Call on every write."""
    path = root / ".gitignore"
    if not path.exists():
        root.mkdir(parents=True, exist_ok=True)
        path.write_text("# qlaudified store: may hold copies of private sources\n*\n", encoding="utf-8")


def safe_name(value: str) -> str:
    """A string usable as one folder name on every OS."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", value) or "unknown"


def session_dir(session_id: str, payload: dict | None = None) -> Path:
    return store_root(payload) / "sessions" / safe_name(session_id)


def long_path(path: str) -> str:
    """Expand Windows 8.3 short names (``C:\\Users\\DRYDEN~1``) to long names.

    Claude Code reports ``%TEMP%`` paths in 8.3 form (Sprint 0). The longest existing prefix is
    expanded, so a path to a file that no longer exists still normalizes. Unchanged off Windows.
    """
    if sys.platform != "win32":  # a plain check, so mypy skips the ctypes code on other OSes
        return path
    if "~" not in path:
        return path
    import ctypes

    buf = ctypes.create_unicode_buffer(32768)
    head, tail = path, ""
    while head:
        n = ctypes.windll.kernel32.GetLongPathNameW(head, buf, len(buf))
        if 0 < n < len(buf):
            return buf.value + tail
        parent, name = os.path.split(head)
        if parent == head:
            break
        head, tail = parent, os.sep + name + tail
    return path


def _is_abs(path: str) -> bool:
    return path.startswith("/") or bool(re.match(r"^[A-Za-z]:/", path))


def normalize(path: str, project: Path | None = None, cwd: str | None = None) -> str:
    """Canonical source string: long names, forward slashes, project-relative when inside it.

    Relative paths (Grep prints them) are taken relative to ``cwd``, else the project.
    """
    p = path.strip().replace("\\", "/")
    if p and not _is_abs(p):
        base = cwd or (str(project) if project is not None else "")
        if base:
            p = base.replace("\\", "/").rstrip("/") + "/" + p
    p = long_path(p.replace("/", os.sep) if sys.platform == "win32" else p).replace("\\", "/")
    p = re.sub(r"/\./", "/", p)
    if project is not None:
        root = long_path(str(project)).replace("\\", "/").rstrip("/") + "/"
        same = p.lower().startswith(root.lower()) if sys.platform == "win32" else p.startswith(root)
        if same:
            return p[len(root):]
    return p


def is_store_path(source: str) -> bool:
    """True for anything under our own store: capturing it would feed the store to itself."""
    s = source.replace("\\", "/").lower()
    return s.startswith(STORE_REL.lower() + "/") or f"/{STORE_REL.lower()}/" in s
