"""Replay layer: recorded sessions through all hooks via qlaudified-sim. Sprint 1-2.

Recordings land in tests/sessions/<name>-<os>/ during Sprint 0 (spike/README.md).
"""

from pathlib import Path

import pytest

SESSIONS = sorted(p for p in (Path(__file__).parent.parent / "sessions").iterdir() if p.is_dir())


@pytest.mark.skipif(not SESSIONS, reason="no recorded sessions yet (Sprint 0)")
@pytest.mark.parametrize("session", SESSIONS, ids=lambda p: p.name)
def test_recording_has_events(session):
    assert (session / "events.jsonl").exists()
