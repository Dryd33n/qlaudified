"""Live smoke tests: real `claude -p` via scripts/live.py. Uses plan usage; run on request only.

Sprint 1 adds the first task (capture fills the store from tests/sandbox/notes).
"""

import pytest

pytestmark = pytest.mark.live


@pytest.mark.skip(reason="Sprint 1")
def test_notes_capture():
    pass
