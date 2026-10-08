"""Replay layer: recorded sessions through the real hook entry point via qlaudified-sim.

Recordings come from Sprint 0 (tests/sessions/<name>-<os>/, made by spike/collect.py).
"""

import csv
import json
from pathlib import Path

import pytest

from qlaudified.testing.sim import replay

SESSIONS = sorted(p for p in (Path(__file__).parent.parent / "sessions").iterdir() if p.is_dir())


@pytest.mark.parametrize("session", SESSIONS, ids=lambda p: p.name)
def test_every_event_exits_zero_with_valid_output(session, tmp_path):
    result = replay(session, tmp_path)
    assert result.calls
    assert [c for c in result.calls if c[1] != 0] == []
    for event, _, out in result.calls:
        if out:
            data = json.loads(out)
            assert event in ("Stop", "PostToolUse", "SessionStart", "MessageDisplay")
            assert set(data) <= {"systemMessage", "hookSpecificOutput"}
    assert not (result.project / ".claude" / ".qlaudified" / "errors.log").exists()


def responses(result, event: str) -> list[dict]:
    return [json.loads(out) for ev, _, out in result.calls if ev == event and out]


def provenance(result, kind: str = "span") -> list[dict]:
    [csv_path] = (result.project / ".claude" / ".qlaudified" / "sessions").glob("*/provenance.csv")
    with open(csv_path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["kind"] == kind]


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


def test_notes_session_injects_deltas_marks_and_verifies(tmp_path):
    result = replay(Path(__file__).parent.parent / "sessions" / "notes-windows", tmp_path)
    deltas = [r["hookSpecificOutput"]["additionalContext"] for r in responses(result, "PostToolUse")]
    assert len(deltas) == 2 and all(len(d) <= 600 for d in deltas)
    assert "source says: estimated, preliminary" in deltas[0]
    assert "[S6 launch-memo.md L3]" in deltas[1] and "q3-update.md" not in deltas[1]  # delta only
    [shown] = responses(result, "MessageDisplay")
    assert "$4.2M, based on preliminary finance figures [S2]." in (
        shown["hookSpecificOutput"]["displayContent"])
    [stop] = responses(result, "Stop")
    assert stop["systemMessage"] == "qlaudified: 2 claims checked · 2 supported"
    claims = provenance(result, "claim")
    assert [(c["verdict"], c["span_ids"]) for c in claims] == [("supported", "S2"), ("supported", "S6")]


def test_compaction_returns_a_digest_of_qualified_spans(tmp_path):
    result = replay(Path(__file__).parent.parent / "sessions" / "interactive-windows", tmp_path)
    [digest] = [r["hookSpecificOutput"]["additionalContext"] for r in responses(result, "SessionStart")]
    assert digest.startswith("Provenance recorded earlier in this session")
    assert len(digest) <= 1200
    assert "q3-update.md L3] Q3 revenue is estimated at $4.2M" in digest
    assert "source says: estimated, preliminary" in digest
    assert "a43f6aeb4f7a460ed" not in digest  # subagent spans stay out of the main digest


def test_repo_session_reports_each_clause(tmp_path):
    result = replay(Path(__file__).parent.parent / "sessions" / "repo-windows", tmp_path)
    [report] = (result.project / ".claude" / ".qlaudified" / "sessions").glob("*/reports/turn-1.md")
    text = report.read_text(encoding="utf-8")
    assert "**supported:** Ledger syncs every 900 seconds" in text
    assert "**supported:** which is 15 minutes." in text
    assert (report.parent / "turn-1.json").exists()


SEEDS = sorted(p for p in SESSIONS if p.name.startswith("seed-"))


def recorded(session: Path) -> list[tuple[str, dict | None]]:
    lines = (session / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [(r["event"], r.get("response")) for r in map(json.loads, lines)]


@pytest.mark.parametrize("session", SEEDS, ids=lambda p: p.name)
def test_seed_replay_answers_where_the_live_run_did(session, tmp_path):
    """Sprint 2 recordings carry the plugin's own live responses: replay must respond to the same
    events, and every seed answer verifies with no problem (each live answer kept its qualifiers)."""
    result = replay(session, tmp_path)
    live = recorded(session)
    assert [(ev, bool(resp)) for ev, resp in live] == [(ev, bool(out)) for ev, _, out in result.calls]
    for stop in responses(result, "Stop"):
        summary = stop["systemMessage"]
        assert "qualifier dropped" not in summary and "contradicted" not in summary, summary


def test_seed_compaction_digest_brings_the_qualifiers_back(tmp_path):
    result = replay(Path(__file__).parent.parent / "sessions" / "seed-compaction-windows", tmp_path)
    [digest] = [r["hookSpecificOutput"]["additionalContext"] for r in responses(result, "SessionStart")]
    assert "[S2 pricing.md L3]" in digest and "subject to change" in digest
    assert "[S4 offices.md L3]" in digest and "source says: may, pending" in digest
