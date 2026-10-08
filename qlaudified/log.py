"""Error and timing log. Never raises (NFR-7)."""

import json
import time
import traceback

from qlaudified.paths import store_root


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
