"""Error, timing and recording logs. Never raises (NFR-7)."""

import json
import os
import time
import traceback

from qlaudified.paths import session_dir, store_root


def log_error(event: str, payload: dict | None, elapsed_ms: float) -> None:
    root = store_root(payload)
    root.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": event,
        "session_id": (payload or {}).get("session_id"),
        "elapsed_ms": round(elapsed_ms, 1),
        "traceback": traceback.format_exc(),
    }
    with open(root / "errors.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def log_timing(event: str, payload: dict | None, elapsed_ms: float, **extra) -> None:
    """One line per hook call in the session's timings.jsonl (NFR-3 evidence)."""
    session_id = (payload or {}).get("session_id")
    if not session_id:
        return
    folder = session_dir(session_id, payload)
    if not folder.is_dir():
        return  # only sessions the store already knows about
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event,
              "tool": (payload or {}).get("tool_name"), "elapsed_ms": round(elapsed_ms, 1), **extra}
    with open(folder / "timings.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def record_event(event: str, payload: dict, response: dict | None) -> None:
    """With ``QLAUDIFIED_RECORD_DIR`` set (``scripts/live.py --record``), append each event and our
    response to ``events.jsonl`` there, in the format spike/collect.py turns into a replay session."""
    folder = os.environ["QLAUDIFIED_RECORD_DIR"]
    os.makedirs(folder, exist_ok=True)
    record = {"event": event, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "payload": payload,
              "response": response}
    with open(os.path.join(folder, "events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
