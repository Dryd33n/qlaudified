"""Replay layer: recorded real sessions through the real hook entry point via qlaudified-sim.

Recordings come from Sprints 0–4 (tests/sessions/<name>-<os>/). Replays run offline, so the
Administrator's sidecar is off and rows carry their rule fields; that's the record Low, Medium
and High all start from (design revision 2).
"""

import csv
import json
from pathlib import Path

import pytest

from qlaudified.testing.sim import replay

SESSIONS_DIR = Path(__file__).parent.parent / "sessions"
SESSIONS = sorted(p for p in SESSIONS_DIR.iterdir() if p.is_dir())


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


def ledger(result, name: str = "provenance.csv") -> list[dict]:
    [path] = (result.project / ".claude" / ".qlaudified" / "sessions").glob(f"*/{name}")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_notes_session_records_one_row_per_fact(tmp_path):
    rows = ledger(replay(SESSIONS_DIR / "notes-windows", tmp_path))
    got = {(r["source"], r["locator"]): r for r in rows}
    assert set(got) == {("q3-update.md", f"L{n}") for n in (3, 4, 5)} | {
        ("launch-memo.md", f"L{n}") for n in (3, 4)}  # headings carry no fact
    assert got[("q3-update.md", "L3")]["source_qualifiers"] == "estimated; preliminary"
    assert got[("launch-memo.md", "L3")]["value"] == "2026-11-18"
    assert got[("launch-memo.md", "L4")]["source_qualifiers"] == "expected to; subject to change"
    # The prompt named both files, so they're provided documents (INT-1).
    assert {r["origin"] for r in rows} == {"Provided Document"}


def test_repo_session_records_grep_and_bash_facts(tmp_path):
    rows = ledger(replay(SESSIONS_DIR / "repo-windows", tmp_path))
    got = {(r["source"], r["locator"]): r for r in rows}
    assert got[("ledger/config.py", "L6")]["claim"] == "SYNC_INTERVAL_S = 900"  # from Grep
    assert got[("ledger/config.py", "L5")]["source_qualifiers"] == "may; roughly"  # from `cat`
    assert got[("ledger/sync.py", "L5")]["origin"] == "Internal Document"  # found, not named
    assert all(r["read_as"] == "code" for r in rows)


def test_subagent_reads_keep_their_agent_id(tmp_path):
    rows = ledger(replay(SESSIONS_DIR / "interactive-windows", tmp_path))
    read = [r for r in rows if r["read_as"] == "local-doc"]
    assert {r["agent_id"] for r in read} == {"main", "a43f6aeb4f7a460ed"}


def test_notes_session_refeeds_deltas_marks_and_verifies(tmp_path):
    result = replay(SESSIONS_DIR / "notes-windows", tmp_path)
    [start] = responses(result, "SessionStart")
    assert "provenance.csv (read-only)" in start["hookSpecificOutput"]["additionalContext"]
    deltas = [r["hookSpecificOutput"]["additionalContext"] for r in responses(result, "PostToolUse")]
    assert len(deltas) == 2 and all(len(d) <= 600 for d in deltas)
    assert "source says: estimated, preliminary" in deltas[0]
    assert "[F4 launch-memo.md L3]" in deltas[1] and "q3-update.md" not in deltas[1]  # delta only
    [shown] = responses(result, "MessageDisplay")
    assert "$4.2M, based on preliminary finance figures [F1]." in (
        shown["hookSpecificOutput"]["displayContent"])
    [stop] = responses(result, "Stop")
    assert stop["systemMessage"] == "qlaudified: 2 claims checked · 2 supported"
    claims = ledger(result, "claims.csv")
    assert [(c["verdict"], c["fact_ids"]) for c in claims] == [("supported", "F1"),
                                                              ("supported", "F4")]
    revenue = next(r for r in ledger(result) if r["fact_id"] == "F1")
    assert revenue["uses"].endswith(":final answer")
    # Kept to the end: the clause stating $4.2M carries "estimated" ("preliminary" is in the next).
    assert revenue["first_use_qualifiers"] == "estimated"


def test_compaction_returns_a_digest_of_qualified_facts(tmp_path):
    result = replay(SESSIONS_DIR / "interactive-windows", tmp_path)
    digest = [r["hookSpecificOutput"]["additionalContext"] for r in responses(result, "SessionStart")
              if r["hookSpecificOutput"]["additionalContext"].startswith("Provenance recorded")]
    assert len(digest) == 1 and len(digest[0]) <= 1200
    assert "provenance.csv" in digest[0].splitlines()[0]
    assert "q3-update.md L3] Q3 revenue is estimated at $4.2M" in digest[0]
    assert "source says: estimated, preliminary" in digest[0]
    assert "a43f6aeb4f7a460ed" not in digest[0]  # subagent facts stay out of the main digest


def test_repo_session_reports_each_clause(tmp_path):
    result = replay(SESSIONS_DIR / "repo-windows", tmp_path)
    [report] = (result.project / ".claude" / ".qlaudified" / "sessions").glob("*/reports/turn-1.md")
    text = report.read_text(encoding="utf-8")
    assert "**supported** (rules): Ledger syncs every 900 seconds" in text
    assert "**supported** (rules): which is 15 minutes." in text
    assert "## Provenance ledger: facts used" in text
    assert (report.parent / "turn-1.json").exists()


SEEDS = sorted(p for p in SESSIONS if p.name.startswith("seed-"))


def recorded(session: Path) -> list[tuple[str, dict | None]]:
    lines = (session / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [(r["event"], r.get("response")) for r in map(json.loads, lines)]


@pytest.mark.parametrize("session", SEEDS, ids=lambda p: p.name)
def test_seed_replay_answers_where_the_live_run_did(session, tmp_path):
    """Sprints 2–3 recordings carry the plugin's own live responses. Replay must refeed, mark and
    report on the same events (SessionStart now always tells Claude where the ledger is), and
    every seed answer verifies with no problem (each live answer kept its qualifiers)."""
    result = replay(session, tmp_path)
    live = [(ev, bool(resp)) for ev, resp in recorded(session) if ev != "SessionStart"]
    now = [(ev, bool(out)) for ev, _, out in result.calls if ev != "SessionStart"]
    assert live == now
    for stop in responses(result, "Stop"):
        summary = stop["systemMessage"]
        assert "qualifier dropped" not in summary and "contradicted" not in summary, summary


def test_seed_compaction_digest_brings_the_qualifiers_back(tmp_path):
    result = replay(SESSIONS_DIR / "seed-compaction-windows", tmp_path)
    digest = next(r["hookSpecificOutput"]["additionalContext"] for r in responses(
        result, "SessionStart") if "Provenance recorded" in r["hookSpecificOutput"]["additionalContext"])
    assert "[F1 pricing.md L3]" in digest and "subject to change" in digest
    assert "[F2 offices.md L3]" in digest and "source says: may, pending" in digest


def test_retry_demo_blocks_once_then_accepts_the_revision(tmp_path):
    """Sprint 4 demo, live: "Q3 revenue was $4.2M." blocked once; the revision restored
    "estimated" and passed. Replayed in High, offline."""
    result = replay(SESSIONS_DIR / "retry-demo-windows", tmp_path, mode="high")
    first, second = responses(result, "Stop")
    assert first["decision"] == "block"
    assert '"Q3 revenue was $4.2M." drops the source\'s qualifier "estimated"' in first["reason"]
    assert "decision" not in second and second["systemMessage"].endswith("1 supported")
