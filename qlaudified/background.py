"""Background jobs beside the hooks: the WebFetch re-fetch (CAP-3) and the High sidecar (SID-1, 2).

A hook writes a job file to ``<session>/pending/`` and launches ``python -S -m <module> <job>``
as a detached process, then returns at once. ``async`` hooks would be killed when a ``claude -p``
session ends (Sprint 3), and a detached process never holds up the agent loop (NFR-4). Stop waits
a few seconds for pending jobs before it verifies. ``QLAUDIFIED_OFFLINE=1`` launches nothing.
"""

import contextlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

WAIT_S = 8.0  # Stop waits at most this long for pending jobs
STALE_S = 60.0  # a job file older than this belongs to a process that died


def pending_dir(session_dir: Path) -> Path:
    return Path(session_dir) / "pending"


def launch(session_dir: Path, module: str, name: str, job: dict) -> Path | None:
    """Write the job file and start the module on it, detached; None when offline."""
    if os.environ.get("QLAUDIFIED_OFFLINE"):
        return None
    folder = pending_dir(session_dir)
    folder.mkdir(parents=True, exist_ok=True)
    pending = folder / f"{name}.json"
    pending.write_text(json.dumps({**job, "session_dir": str(session_dir),
                                   "started": time.time()}), encoding="utf-8")
    root = Path(__file__).resolve().parent.parent
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL, "cwd": str(root), "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, "-S", "-m", module, str(pending)], **kwargs)
    return pending


def wait_for_pending(session_dir: Path, max_s: float = WAIT_S) -> None:
    """Let in-flight jobs finish before Stop verifies; stale ones are skipped."""
    folder = pending_dir(session_dir)
    deadline = time.time() + max_s
    while folder.is_dir():
        live = [p for p in folder.glob("*.json") if time.time() - p.stat().st_mtime < STALE_S]
        if not live or time.time() > deadline:
            return
        time.sleep(0.1)


def run_job(argv: list[str], runner: Callable[[dict], object], event: str) -> int:
    """Entry point for a detached job: run it, always remove the job file, log, never raise."""
    os.environ.setdefault("QLAUDIFIED_NESTED", "1")
    pending = Path(argv[0])
    job: dict = {}
    try:
        job = json.loads(pending.read_text(encoding="utf-8"))
        runner(job)
    except Exception:  # noqa: BLE001 - detached: log, never raise
        with contextlib.suppress(Exception):
            from qlaudified.log import log_error

            log_error(event, {"cwd": job.get("project")}, 0.0)
    finally:
        pending.unlink(missing_ok=True)
    return 0
