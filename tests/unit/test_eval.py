"""Eval runner planning and offline scoring on hand-built run folders (no live runs).

Design revision 2 conditions: off (no plugin, so no ledger), low (record only), medium (record +
refeed), high (+ retry)."""

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
             variant: str = "natural", first_use: str | None = None, sidecar_cost: float = 0.0,
             consulted: bool = False):
    """A finished run. Off runs have no ledger; the others get one row per fact in the task's
    files, as Provided Documents (the prompts name their files), first used with ``first_use``."""
    folder = runs / f"{task}__{variant}__{condition}__r{repeat}__haiku"
    folder.mkdir(parents=True)
    if condition != "off":
        sandbox = REPO / "tests" / "sandbox" / task
        files = sorted(str(p.relative_to(sandbox)).replace("\\", "/") for p in sandbox.rglob("*.md"))
        store = Store(folder / "store" / "sessions" / "s1")
        for span in spans_from_files(sandbox, *files):
            span.span_id = ""
            span.category = "Provided Document"
            if first_use is not None:
                span.first_use_step, span.first_use_qualifiers = 2, first_use
            store.add_span(span)
        store.close()
        session = store.session_dir
        (session / "timings.jsonl").write_text(
            json.dumps({"event": "PostToolUse", "elapsed_ms": 90.0}) + "\n"
            + json.dumps({"event": "Stop", "elapsed_ms": 120.0}) + "\n", encoding="utf-8")
        if sidecar_cost:
            (session / "usage.jsonl").write_text(json.dumps({"cost_usd": sidecar_cost}) + "\n")
        if consulted:
            (session / "consults.jsonl").write_text(json.dumps({"step": 3}) + "\n")
    (folder / "result.json").write_text(json.dumps({
        "task": task, "variant": variant, "condition": condition, "model": "haiku",
        "returncode": 0, "total_cost_usd": cost, "result": answer}), encoding="utf-8")


def cells(markdown: str) -> dict[str, list[str]]:
    return {line.split(" | ")[0].strip("| "): line.split(" | ")
            for line in markdown.splitlines()[2:] if line.startswith("| ")}


DROPPED = "Fernwick's Q3 revenue was $4.2M."
KEPT = "Fernwick's Q3 revenue is estimated at $4.2M [F1]."


def test_scores_every_measure_per_condition(score, tmp_path):
    make_run(tmp_path, "seed-hedged", "off", DROPPED, 0.0020)
    make_run(tmp_path, "seed-hedged", "low", DROPPED, 0.0020, first_use="", sidecar_cost=0.0006)
    make_run(tmp_path, "seed-hedged", "medium", KEPT, 0.0020, first_use="estimated",
             sidecar_cost=0.0006, consulted=True)
    make_run(tmp_path, "seed-nosource", "off", "Fernwick's Q4 revenue was $5.1M.", 0.0018)
    make_run(tmp_path, "seed-nosource", "low", "Fernwick's Q4 revenue was $5.1M.", 0.0018)
    make_run(tmp_path, "seed-nosource", "medium", "The file doesn't give Q4 revenue.", 0.0018)
    rows = cells(score.table(score.load_runs(tmp_path)))
    assert set(rows) == {"off", "low", "medium"}
    off, low, medium = rows["off"], rows["low"], rows["medium"]
    assert off[2].startswith("0% (0/1)") and off[4].startswith("100% (1/1)")  # dropped, uncaught
    assert off[3] == off[5] == off[6] == "n/a"  # no plugin, no ledger
    assert low[2].startswith("0% (0/1)") and low[4].startswith("0% (0/1)")  # the report flagged it
    assert low[3] == "0% (0/1)"  # dropped at first use too
    assert low[5] == "100% (2/2) / 100% (2/2) / 100% (2/2)"  # seed-hedged's 2 planted facts
    assert low[6] == "100% (2/2)"  # the dropped fact and the invented Q4 figure
    assert medium[2].startswith("100% (1/1)") and medium[3] == "100% (1/1)"
    assert medium[7] == "50% (1/2)" and low[7] == "n/a"  # consults: medium and high only
    assert low[9] == "+15.0%"  # +30% on seed-hedged, 0% on seed-nosource
    assert low[10] == "$0.00010"  # $0.0006 of sidecar over 6 rows
    assert medium[11] == "90 ms" and medium[12].startswith("120 ms")


def test_decay_table_and_the_headline_comparison(score, tmp_path):
    answers = {"decay-finance": ("Q3 revenue was $4.2M.", "Q3 revenue is estimated at $4.2M."),
               "decay-launch": ("The launch is on March 3, 2027.",
                                "The launch is tentatively set for March 3, 2027.")}
    for scenario, (dropped, kept) in answers.items():
        for variant in ("d0", "d5", "d15"):
            task = f"{scenario}-{variant}"
            make_run(tmp_path, task, "low", kept if variant == "d0" else dropped, 0.002)
            make_run(tmp_path, task, "medium", kept, 0.002)
    runs = score.load_runs(tmp_path)
    rows = score.scored_rows(runs)
    decay = cells(score.decay_table(rows))
    assert [c.strip(" |") for c in decay["low"][1:4]] == ["100% (2/2)", "0% (0/2)", "0% (0/2)"]
    assert [c.strip(" |") for c in decay["medium"][1:4]] == ["100% (2/2)"] * 3
    report = score.report(runs)
    assert "Qualifiers kept by distance (decay tasks):" in report
    assert "- qualifiers kept, medium vs low on decay tasks at ~5 and ~15 steps: +100 points" in report


def test_paired_comparison_and_task_bootstrap(score, tmp_path):
    facts = {"seed-hedged": (DROPPED, "Fernwick's Q3 revenue is estimated at $4.2M."),
             "single-churn": ("Monthly churn was 3.1% in Q3.", "Monthly churn was roughly 3.1% in Q3."),
             "single-pricing": ("The Team plan costs $15 per seat per month.",
                                "The Team plan is expected to cost $15 per seat per month.")}
    for i, (task, (dropped, kept)) in enumerate(facts.items()):
        make_run(tmp_path, task, "low", dropped, 0.002)
        make_run(tmp_path, task, "medium", kept if i else dropped, 0.002)
    rows = score.scored_rows(score.load_runs(tmp_path))
    result = score.compare(rows, "low", "medium", score.METRICS["qualifiers kept"])
    assert result["tasks"] == 3 and round(result["diff"], 2) == 0.67
    lo, hi = result["ci"]
    assert 0 <= lo <= result["diff"] <= hi <= 1
    assert score.report(score.load_runs(tmp_path)).startswith("## haiku · natural prompts")


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
    assert out[0] == "32 runs planned, 1 already done, 31 to run"
    assert out[1].strip() == "seed-hedged__natural__low__r1__haiku"
    assert out[8].strip() == "seed-hedged__pressure__off__r1__haiku"  # r1 of everything first
    assert out[16].strip() == "seed-hedged__natural__off__r2__haiku"
    assert run.CONDITIONS["off"] is None  # off runs without the plugin


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
    [row] = score.scored_rows(score.load_runs(tmp_path))
    assert (row.get("stated"), row.get("kept", 0)) == (1, kept)
