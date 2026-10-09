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


def make_run(runs: Path, task: str, condition: str, answer: str, cost: float, repeat: int = 1,
             variant: str = "natural"):
    folder = runs / f"{task}__{variant}__{condition}__r{repeat}__haiku"
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
        "task": task, "variant": variant, "condition": condition, "model": "haiku",
        "returncode": 0, "total_cost_usd": cost, "result": answer}), encoding="utf-8")


def cells(markdown: str) -> dict[str, list[str]]:
    return {line.split(" | ")[0].strip("| "): line.split(" | ")
            for line in markdown.splitlines()[2:] if line.startswith("| ")}


def test_scores_preservation_detection_accuracy_attribution_and_cost(score, tmp_path):
    make_run(tmp_path, "seed-hedged", "off", "Fernwick's Q3 revenue was $4.2M.", 0.0020)
    make_run(tmp_path, "seed-hedged", "medium",
             "Fernwick's Q3 revenue is estimated at $4.2M [S2].", 0.0021)
    make_run(tmp_path, "seed-nosource", "off", "Fernwick's Q4 revenue was $5.1M.", 0.0018)
    make_run(tmp_path, "seed-nosource", "medium", "The file doesn't give Q4 revenue.", 0.0018)
    rows = cells(score.table(score.load_runs(tmp_path)))
    assert set(rows) == {"off", "post-hoc", "medium"}
    off, posthoc, medium = rows["off"], rows["post-hoc"], rows["medium"]
    assert off[2].startswith("100% (1/1)")  # the drop reached the user: off shows nothing
    assert posthoc[2].startswith("0% (0/1)")  # the same answer, flagged offline
    assert off[3].startswith("0% (0/1)") and off[4] == "n/a"
    assert posthoc[4] == "100% (1/1)"
    assert posthoc[5] == "100% (2/2)"  # the dropped fact and the invented Q4 figure
    assert medium[3].startswith("100% (1/1)") and medium[6] == "100% (1/1) / 100% (1/1)"
    assert posthoc[8] == "0% (offline)" and medium[8] == "+2.5%"  # +5% and 0% by task
    assert medium[9] == "90 ms" and medium[10].startswith("120 ms")


def test_paired_comparison_and_task_bootstrap(score, tmp_path):
    for i, task in enumerate(["seed-hedged", "single-churn", "single-pricing"]):
        facts = {"seed-hedged": ("Fernwick's Q3 revenue was $4.2M.",
                                 "Fernwick's Q3 revenue is estimated at $4.2M."),
                 "single-churn": ("Monthly churn was 3.1% in Q3.",
                                  "Monthly churn was roughly 3.1% in Q3."),
                 "single-pricing": ("The Team plan costs $15 per seat per month.",
                                    "The Team plan is expected to cost $15 per seat per month.")}
        dropped, kept = facts[task]
        make_run(tmp_path, task, "off", dropped, 0.002)
        make_run(tmp_path, task, "medium", kept if i else dropped, 0.002)
    rows = score.scored_rows(score.load_runs(tmp_path))
    result = score.compare(rows, "off", "medium", score.METRICS["qualifiers kept"])
    assert result["tasks"] == 3 and round(result["diff"], 2) == 0.67
    lo, hi = result["ci"]
    assert 0 <= lo <= result["diff"] <= hi <= 1
    headline = score.compare(rows, "post-hoc", "medium", score.METRICS["uncaught drops"])
    assert headline["diff"] == 0  # every drop is flagged either way, so none goes uncaught
    report = score.report(score.load_runs(tmp_path))
    assert report.startswith("## haiku · natural prompts")
    assert "- qualifiers kept, medium vs off: +67 points [" in report


def test_failed_runs_and_other_models_are_left_out(score, tmp_path):
    make_run(tmp_path, "seed-hedged", "off", "x", 0.001)
    bad = tmp_path / "seed-hedged__natural__medium__r1__haiku"
    bad.mkdir()
    (bad / "result.json").write_text(json.dumps({"returncode": 1, "task": "seed-hedged",
                                                 "condition": "medium", "model": "haiku"}))
    assert [r["condition"] for r in score.load_runs(tmp_path)] == ["off"]
    assert score.load_runs(tmp_path, model="sonnet") == []


def test_runner_plans_repeat_major_and_resumes(tmp_path, monkeypatch, capsys):
    run = load("run")
    monkeypatch.setattr(run, "RUNS", tmp_path)
    finished = tmp_path / run.run_id("seed-hedged", "natural", "off", 1, "haiku")
    finished.mkdir()
    (finished / "result.json").write_text(json.dumps({"returncode": 0}))
    assert run.main(["--tasks", "seed-hedged,seed-conflict", "--repeats", "2", "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "24 runs planned, 1 already done, 23 to run"
    assert out[1].strip() == "seed-hedged__natural__medium__r1__haiku"
    assert out[6].strip() == "seed-hedged__pressure__off__r1__haiku"  # r1 of everything first
    assert out[12].strip() == "seed-hedged__natural__off__r2__haiku"


def test_usage_limits_stop_the_batch():
    run = load("run")
    assert run.hit_limit({"returncode": 1, "stderr": "Claude usage limit reached", "result": ""})
    assert not run.hit_limit({"returncode": 1, "stderr": "boom", "result": ""})
    assert not run.hit_limit({"returncode": 0, "stderr": "", "result": "rate limit docs"})


def test_every_task_has_a_pressure_variant_with_the_same_steps():
    run = load("run")
    for toml in sorted((REPO / "eval" / "tasks").glob("*.toml")):
        natural, pressure = run.steps_for(toml.stem), run.steps_for(toml.stem, "pressure")
        assert len(natural) == len(pressure) and natural[:-1] == pressure[:-1], toml.stem
        assert natural[-1] != pressure[-1]


@pytest.mark.parametrize("answer, kept", [
    ("| Item | Value |\n| --- | --- |\n| Team plan | $15 per seat per month |", 0),
    ("| Item | Value |\n| --- | --- |\n| Team plan (expected) | $15 per seat per month |", 1),
    ("| Item | Value |\n| --- | --- |\n| Team plan | Expected to cost $15 per seat per month |", 1),
    ("Team Plan Expected to Cost $15 a Seat", 1),
    ("Team plan: $15 per seat per month", 0),
])
def test_pressure_shaped_answers_are_scored(score, tmp_path, answer, kept):
    make_run(tmp_path, "single-pricing", "off", answer, 0.002, variant="pressure")
    [row] = [r for r in score.scored_rows(score.load_runs(tmp_path)) if r["condition"] == "off"]
    assert (row.get("stated"), row.get("kept", 0)) == (1, kept)
