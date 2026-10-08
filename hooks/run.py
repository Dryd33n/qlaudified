"""Single hook entry point: ``run.py <event>``, launched by hooks.json as ``py -3`` or ``python3``.

Reads the hook payload from stdin, dispatches to ``qlaudified.hooks.<module>.handle`` with a
lazy import, prints any JSON response, and always exits 0 (NFR-7). This file must stay valid on old
Pythons so it can explain the 3.11 floor instead of crashing on the package's newer syntax.
"""

import contextlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_PYTHON = (3, 11)
EVENTS = {
    "PostToolUse": "post_tool_use",
    "SessionStart": "session_start",
    "Stop": "stop",
    "MessageDisplay": "message_display",
}


def old_python(event: str, raw: str) -> None:
    """Python too old: log it once per project, tell the user at each session start, capture nothing."""
    found = "%d.%d.%d" % tuple(sys.version_info[:3])
    message = (
        "qlaudified needs Python %d.%d+, but its hooks ran on Python %s (%s), so no provenance is "
        "being recorded. Install Python 3.11 or newer from python.org (on Windows, keep the py "
        "launcher option ticked)." % (MIN_PYTHON + (found, sys.executable))
    )
    with contextlib.suppress(Exception):
        payload = json.loads(raw) if raw.strip() else {}
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        store = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd(),
                             ".claude", ".qlaudified")
        marker = os.path.join(store, "python-too-old")
        if not os.path.exists(marker):
            os.makedirs(store, exist_ok=True)
            with open(os.path.join(store, "errors.log"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event,
                                    "error": message}) + "\n")
            with open(marker, "w", encoding="utf-8") as f:
                f.write(found + "\n")
    if event == "SessionStart":
        sys.stdout.write(json.dumps({"systemMessage": message}))


def main() -> int:
    start = time.perf_counter()
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = None
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        if sys.version_info < MIN_PYTHON:
            old_python(event, raw)
            return 0
        payload = json.loads(raw) if raw.strip() else {}
        module_name = EVENTS.get(event)
        if module_name is None or not isinstance(payload, dict):
            return 0
        import importlib

        module = importlib.import_module(f"qlaudified.hooks.{module_name}")
        response = module.handle(payload)
        if response:
            sys.stdout.write(json.dumps(response))
        from qlaudified.log import log_timing

        log_timing(event, payload, elapsed_ms=(time.perf_counter() - start) * 1000)
    except Exception:  # noqa: BLE001 - hooks must never break a session
        with contextlib.suppress(Exception):  # logging failed too; still exit 0
            from qlaudified.log import log_error

            log_error(event, payload if isinstance(payload, dict) else None,
                      elapsed_ms=(time.perf_counter() - start) * 1000)
    return 0


if __name__ == "__main__":
    sys.exit(main())
