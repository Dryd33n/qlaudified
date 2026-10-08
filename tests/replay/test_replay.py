"""Replay layer: recorded sessions through the real hook entry point via qlaudified-sim.

Recordings come from Sprint 0 (tests/sessions/<name>-<os>/, made by spike/collect.py).
"""

import csv
from pathlib import Path

import pytest

from qlaudified.testing.sim import replay

SESSIONS = sorted(p for p in (Path(__file__).parent.parent / "sessions").iterdir() if p.is_dir())


@pytest.mark.parametrize("session", SESSIONS, ids=lambda p: p.name)
def test_every_event_exits_zero_and_injects_nothing(session, tmp_path):
    result = replay(session, tmp_path)
    assert result.calls
    assert [c for c in result.calls if c[1] != 0] == []
    assert [c for c in result.calls if c[2]] == []  # Sprint 1 never writes to stdout
    assert not (result.project / ".claude" / ".qlaudified" / "errors.log").exists()


def provenance(result) -> list[dict]:
    [csv_path] = (result.project / ".claude" / ".qlaudified" / "sessions").glob("*/provenance.csv")
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_notes_session_produces_the_expected_provenance(tmp_path):
    rows = provenance(replay(Path(__file__).parent.parent / "sessions" / "notes-windows", tmp_path))
    got = {(r["source"], r["locator"]): r for r in rows}
    assert set(got) == {("q3-update.md", f"L{n}") for n in (1, 3, 4, 5)} | {
        ("launch-memo.md", f"L{n}") for n in (1, 3, 4)}
    assert got[("q3-update.md", "L3")]["qualifiers"] == "estimated; preliminary"
    assert got[("launch-memo.md", "L3")]["numbers"] == "2026-11-18"
    assert got[("launch-memo.md", "L4")]["qualifiers"] == "expected to; subject to change"


def test_repo_session_records_grep_and_bash(tmp_path):
    rows = provenance(replay(Path(__file__).parent.parent / "sessions" / "repo-windows", tmp_path))
    sources = {(r["source"], r["locator"]) for r in rows}
    assert ("ledger/config.py", "L6") in sources  # from Grep
    assert ("ledger/config.py", "L3-L6") in sources  # from `cat` via Bash
    assert all(r["origin"] == "code" for r in rows)


def test_subagent_reads_keep_their_agent_id(tmp_path):
    rows = provenance(replay(Path(__file__).parent.parent / "sessions" / "interactive-windows", tmp_path))
    assert {r["agent_id"] for r in rows} == {"main", "a43f6aeb4f7a460ed"}
