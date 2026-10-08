"""Single hook entry point: ``python hooks/run.py <event>``.

Reads the hook payload from stdin, dispatches to ``qlaudified.hooks.<module>.handle`` with a
lazy import, prints any JSON response, and always exits 0 (NFR-7).
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EVENTS = {
    "PostToolUse": "post_tool_use",
    "SessionStart": "session_start",
    "Stop": "stop",
    "MessageDisplay": "message_display",
}


def main() -> int:
    start = time.perf_counter()
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = None
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        payload = json.loads(raw) if raw.strip() else {}
        module_name = EVENTS.get(event)
        if module_name is None:
            return 0
        import importlib

        module = importlib.import_module(f"qlaudified.hooks.{module_name}")
        response = module.handle(payload)
        if response:
            sys.stdout.write(json.dumps(response))
    except Exception:  # noqa: BLE001 - hooks must never break a session
        try:
            from qlaudified.log import log_error

            log_error(event, payload, elapsed_ms=(time.perf_counter() - start) * 1000)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
