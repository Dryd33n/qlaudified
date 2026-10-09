"""Live smoke tests: real `claude -p` via scripts/live.py with this plugin. Uses plan usage.

Run on request only: `pytest -m live tests/live -k <name>` (CLAUDE.md: ask before running more
than one). Each test reads the sandbox path from the run's ledger line in eval/ledger.jsonl.
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.live

REPO = Path(__file__).resolve().parents[2]


def run_live(task: str) -> dict:
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "live.py"), task, "--record"],
                          cwd=REPO, capture_output=True, timeout=600, check=False)
    ledger = (REPO / "eval" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(ledger[-1])
    assert record["task"] == task and proc.returncode == 0, proc.stderr.decode(errors="replace")
    return record


def store(record: dict) -> Path:
    return Path(record["sandbox"]) / ".claude" / ".qlaudified"


def provenance(record: dict, name: str = "provenance.csv") -> list[dict]:
    paths = list((store(record) / "sessions").glob(f"*/{name}"))
    assert len(paths) == 1, f"expected one session store, found {paths}"
    with open(paths[0], newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("task, expected", [
    ("notes", {("q3-update.md", "L3"), ("launch-memo.md", "L3")}),
    ("repo", {("ledger/config.py", "L6")}),
])
def test_capture_fills_provenance_csv(task, expected):
    record = run_live(task)
    rows = provenance(record)
    assert expected <= {(r["source"], r["locator"]) for r in rows}
    assert not (store(record) / "errors.log").exists()
    timings = [json.loads(line) for line in
               next((store(record) / "sessions").glob("*/timings.jsonl")).read_text().splitlines()]
    # In process; the sidecar call (when the step qualifies) is the bulk of it (NFR-4: <= 10 s).
    assert all(t["elapsed_ms"] < 10_000 for t in timings if t["event"] == "PostToolUse")


def test_mode_skill_saves_the_project_default():
    record = run_live("mode")
    assert 'mode = "high"' in (store(record) / "config.toml").read_text(encoding="utf-8")


def test_medium_records_refeeds_and_reports():
    """Design revision 2: the ledger fills step by step with REQ-3.2 rows, the Administrator runs,
    the answer is verified, and the report is saved."""
    record = run_live("seed-hedged")
    [folder] = (store(record) / "sessions").glob("*")
    rows = provenance(record)
    assert rows and {r["origin"] for r in rows} == {"Provided Document"}
    assert all(r["uses"] for r in rows if r["claim"].startswith("Q3 revenue"))
    claims = provenance(record, "claims.csv")
    assert claims and all(r["verdict"] in ("supported", "qualifier-dropped") for r in claims)
    usage = [json.loads(line) for line in (folder / "usage.jsonl").read_text().splitlines()]
    assert {u["tier"] for u in usage} >= {"administrator", "administrator-report"}
    assert (folder / "reports" / "turn-1.md").exists() and (folder / "reports" / "turn-1.json").exists()
    timings = [json.loads(line) for line in (folder / "timings.jsonl").read_text().splitlines()]
    assert {t["event"] for t in timings} >= {"PostToolUse", "MessageDisplay", "Stop"}
    assert not (store(record) / "errors.log").exists()
