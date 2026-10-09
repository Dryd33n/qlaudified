"""Eval runner planning and offline scoring on hand-built run folders (no live runs)."""

import importlib.util
import json
from pathlib import Path

import pytest

from qlaudified.store import Store
from qlaudified.testing.spans import spans_from_files

REPO = Path(__file__).resolve().parents[2]


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"eval_{name}", REPO / "eval" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def score():
    return load("score")


def make_run(runs: Path, task: str, condition: str, answer: str, cost: float, repeat: int = 1):
    folder = runs / f"{task}__{condition}__r{repeat}__haiku"
    sandbox = REPO / "tests" / "sandbox" / task
    files = sorted(str(p.relative_to(sandbox)).replace("\\", "/") for p in sandbox.rglob("*.md"))
    store = Store(folder / "store" / "sessions" / "s1")
    for span in spans_from_files(sandbox, *files):
        span.span_id = ""
        store.add_span(span)
    (store.session_dir / "timings.jsonl").write_text(
        json.dumps({"event": "PostToolUse", "elapsed_ms": 90.0}) + "\n"
        + json.dumps({"event": "Stop", "elapsed_ms": 120.0}) + "\n", encoding="utf-8")
    (folder / "result.json").write_text(json.dumps({
        "task": task, "condition": condition, "model": "haiku", "returncode": 0,
        "total_cost_usd": cost, "result": answer}), encoding="utf-8")


def test_scores_preservation_detection_accuracy_attribution_and_cost(score, tmp_path):
    make_run(tmp_path, "seed-hedged", "off", "Fernwick's Q3 revenue was $4.2M.", 0.0020)
    make_run(tmp_path, "seed-hedged", "medium",
             "Fernwick's Q3 revenue is estimated at $4.2M [S2].", 0.0021)
    make_run(tmp_path, "seed-nosource", "off", "Fernwick's Q4 revenue was $5.1M.", 0.0018)
    make_run(tmp_path, "seed-nosource", "medium", "The file doesn't give Q4 revenue.", 0.0018)
    rows = {line.split(" | ")[0].strip("| "): line.split(" | ")
            for line in score.table(score.load_runs(tmp_path)).splitlines()[2:]}
    assert set(rows) == {"off", "post-hoc", "medium"}
    off, posthoc, medium = rows["off"], rows["post-hoc"], rows["medium"]
    assert off[2] == "0% (0/1)" and off[3] == "n/a"  # dropped "estimated"; shows nothing
    assert posthoc[3] == "100% (1/1)"  # the same answer, flagged offline
    assert posthoc[4] == "100% (2/2)"  # the dropped fact and the invented Q4 figure
    assert medium[2] == "100% (1/1)" and medium[5] == "100% (1/1) / 100% (1/1)"
    assert posthoc[7] == "0% (offline)" and medium[7] == "+2.5%"  # +5% on one task, 0% on the other
    assert medium[8] == "90 ms" and medium[9].startswith("120 ms")


def test_failed_runs_and_other_models_are_left_out(score, tmp_path):
    make_run(tmp_path, "seed-hedged", "off", "x", 0.001)
    bad = tmp_path / "seed-hedged__medium__r1__haiku"
    bad.mkdir()
    (bad / "result.json").write_text(json.dumps({"returncode": 1, "task": "seed-hedged",
                                                 "condition": "medium", "model": "haiku"}))
    assert [r["condition"] for r in score.load_runs(tmp_path)] == ["off"]
    assert score.load_runs(tmp_path, model="sonnet") == []


def test_runner_plans_repeat_major_and_resumes(tmp_path, monkeypatch, capsys):
    run = load("run")
    monkeypatch.setattr(run, "RUNS", tmp_path)
    finished = tmp_path / run.run_id("seed-hedged", "off", 1, "haiku")
    finished.mkdir()
    (finished / "result.json").write_text(json.dumps({"returncode": 0}))
    assert run.main(["--tasks", "seed-hedged,seed-conflict", "--repeats", "2", "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "12 runs planned, 1 already done, 11 to run"
    assert out[1].strip() == "seed-hedged__medium__r1__haiku"  # r1 of everything comes first
    assert out[5].strip() == "seed-conflict__high__r1__haiku"
    assert run.steps_for("seed-compaction")[1] == "/compact"
