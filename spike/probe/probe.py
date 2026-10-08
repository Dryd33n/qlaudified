"""Sprint 0 probe hook: records every payload it receives. Throwaway; Python 3.7+ compatible.

Usage (from hooks.json): <python> probe.py <EventName>

Env:
  QLAUDIFIED_RECORD_DIR    write events.jsonl here
                           (default: <project>/.qlaudified-probe/<session_id>/)
  QLAUDIFIED_PROBE_INJECT  1 = answer PostToolUse and SessionStart with a fixed provenance line
                           as additionalContext, to check it reaches Claude
  QLAUDIFIED_PROBE_NESTED  1 = on Stop, run a nested `claude -p --safe-mode` and record its timing
  QLAUDIFIED_PROBE_MODEL   model for the nested call (default: haiku)
"""

import json
import os
import subprocess
import sys
import time

T0 = time.perf_counter()

INJECT_LINE = (
    "[S1 notes/q3-update.md L3] Q3 revenue 4.2M USD; source says: estimated, preliminary"
)
SECRET_HINTS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "AUTH")


def respond(event, payload):
    if os.environ.get("QLAUDIFIED_PROBE_INJECT") == "1" and event in ("PostToolUse", "SessionStart"):
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": INJECT_LINE}}
    return None


def nested_call():
    model = os.environ.get("QLAUDIFIED_PROBE_MODEL", "haiku")
    cmd = ["claude", "-p", "--safe-mode", "--model", model, "--output-format", "json",
           "Reply with the single word OK."]
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=120, shell=(os.name == "nt"))
        out = proc.stdout.decode("utf-8", "replace")
        result = {"returncode": proc.returncode, "stdout": out[:2000],
                  "stderr": proc.stderr.decode("utf-8", "replace")[:2000]}
    except Exception as e:  # noqa: BLE001
        result = {"error": repr(e)}
    result["cmd"] = cmd
    result["wall_ms"] = round((time.perf_counter() - start) * 1000, 1)
    return result


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    payload, parse_error = None, None
    try:
        payload = json.loads(raw) if raw.strip() else None
    except ValueError as e:
        parse_error = str(e)

    session = payload.get("session_id", "no-session") if isinstance(payload, dict) else "no-session"
    out_dir = os.environ.get("QLAUDIFIED_RECORD_DIR") or os.path.join(
        os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(), ".qlaudified-probe", session)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    output = respond(event, payload)
    record = {
        "event": event,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "argv": sys.argv[1:],
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "env": {k: v for k, v in os.environ.items()
                if k.startswith("CLAUDE") and not any(h in k for h in SECRET_HINTS)},
        "stdin_bytes": len(raw),
        "payload": payload,
        "raw": raw if payload is None else None,
        "parse_error": parse_error,
        "stdout": output,
    }
    if event == "Stop" and os.environ.get("QLAUDIFIED_PROBE_NESTED") == "1":
        record["nested"] = nested_call()
    record["elapsed_ms"] = round((time.perf_counter() - T0) * 1000, 1)

    with open(os.path.join(out_dir, "events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    if output:
        sys.stdout.write(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - a probe must never break the session
        sys.stderr.write("probe error: %r\n" % (e,))
    sys.exit(0)
