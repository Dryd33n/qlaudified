"""Hook contract: run.py never fails a session, whatever it is fed (NFR-7)."""

import json

import pytest

EVENTS = ["PostToolUse", "SessionStart", "Stop", "MessageDisplay", "UserPromptSubmit",
          "UnknownEvent", ""]


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.parametrize("payload", ["", "not json", "{}", '{"session_id": "s1"}'])
def test_exits_zero_and_stays_quiet(run_hook, event, payload):
    proc = run_hook(event, payload)
    assert proc.returncode == 0
    if event == "SessionStart" and "session_id" in payload:
        # Medium tells Claude where the ledger is (RFD-1), and nothing else.
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        assert "provenance.csv" in out["additionalContext"]
        return
    assert proc.stdout == b""
