"""Hook contract: run.py never fails a session, whatever it is fed (NFR-7)."""

import pytest

EVENTS = ["PostToolUse", "SessionStart", "Stop", "MessageDisplay", "UnknownEvent", ""]


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.parametrize("payload", ["", "not json", "{}", '{"session_id": "s1"}'])
def test_exits_zero_and_stays_quiet(run_hook, event, payload):
    proc = run_hook(event, payload)
    assert proc.returncode == 0
    assert proc.stdout == b""
