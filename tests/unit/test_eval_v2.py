"""Study v2 tooling (docs/findings/protocol-v2.md): task build, independent scorer, statistics,
transcript distance and runner conditions. No live runs."""

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "eval" / "v2"
sys.path.insert(0, str(V2))

build = importlib.import_module("build")
calib = importlib.import_module("calib")
cues = importlib.import_module("cues")
figures = importlib.import_module("figures")
labels = importlib.import_module("labels")
stats = importlib.import_module("stats")
transcript = importlib.import_module("transcript")


def task(name: str) -> dict:
    return json.loads((V2 / "tasks" / f"{name}.json").read_text(encoding="utf-8"))


def outcomes(answer: str, name: str = "halden-trial-near") -> dict[str, str]:
    return {s.fact: s.outcome for s in calib.score_answer(answer, task(name)["facts"])}


# --- the task set ----------------------------------------------------------------------------

def test_committed_task_set_matches_the_families():
    """Frozen task set: the build from families/*.toml equals what MANIFEST.json records."""
    assert build.main(["--check"]) == 0


def test_every_family_is_valid_and_mixes_hedged_with_firm_facts():
    families = build.load_families()
    assert len(families) >= 16
    assert [p for fam in families for p in build.validate(fam)] == []
    assert {fam["scope"] for fam in families} == {"sentence", "heading", "footnote", "table",
                                                  "citation"}


def test_far_tasks_read_every_distractor_before_the_question():
    t = task("corran-fuel-far")
    steps = (V2 / "sandbox" / t["id"] / "prompt-format.txt").read_text(encoding="utf-8").split("\n---\n")
    assert len(steps) == 7 and t["distractors"][-1] == "operating-report.md"
    assert steps[-1].startswith("From what you read earlier")
    assert t["distance_tokens"] > 1000


def test_prompt_styles_differ_only_in_the_final_step():
    for t in ("maple-roads-near", "bright-arr-far"):
        files = {s: (V2 / "sandbox" / t / f"prompt-{s}.txt").read_text(encoding="utf-8").split("\n---\n")
                 for s in ("natural", "format", "antihedge")}
        assert files["natural"][:-1] == files["format"][:-1] == files["antihedge"][:-1]
        assert "no hedging" in files["antihedge"][-1] and "no hedging" not in files["format"][-1]


def test_the_scorer_imports_nothing_from_the_plugin():
    """Methods critique, fix 6: the judge is not built from the defendant's parts."""
    for path in V2.glob("*.py"):
        assert not re.search(r"^\s*(from|import)\s+qlaudified", path.read_text(encoding="utf-8"),
                             re.MULTILINE), path.name


# --- figures and cues ------------------------------------------------------------------------

@pytest.mark.parametrize("text, value, unit, ok", [
    ("$2.7M", 2700000, "USD", True), ("$2.7 million", 2700000, "USD", True),
    ("$2,700,000", 2700000, "USD", True), ("2.7M dollars", 2700000, "USD", True),
    ("$52M", 51900000, "USD", True), ("$2.3M", 2700000, "USD", False),
    ("93.5%", 93.5, "%", True), ("99.9%", 99.95, "%", False), ("12 percent", 12, "%", True),
    ("14% of roles", 14, "count", False), ("$38", 38, "km", False),
    ("June 12, 2027", "2027-06-12", "date", True), ("12 June 2027", "2027-06-12", "date", True),
    ("June 12", "2027-06-12", "date", True), ("June 13, 2027", "2027-06-12", "date", False),
    ("in Q3", 3, "count", False), ("HB-204", 204, "count", False), ("ops-1.md", 1, "count", False),
])
def test_figures_match_values_and_skip_labels(text, value, unit, ok):
    assert any(figures.matches(f, value, unit) for f in figures.extract(text)) is ok


@pytest.mark.parametrize("text, hedged", [
    ("Q3 spend is estimated at $2.7M", True), ("ARR ~$51.9M", True),
    ("subject to the audit", True), ("not yet final", True), ("Fuel could reach $3.4M", True),
    ("386 of a planned 520 patients", False), ("against the 99.5% SLA target", False),
    ("Launch on May 3, 2027", False), ("an update about the trial", False),
    ("Business plan: $29", False), ("Uptime was 99.95% in July", False),
])
def test_cues_find_hedges_but_not_their_lookalikes(text, hedged):
    assert cues.hedged(text) is hedged


# --- calibration -----------------------------------------------------------------------------

def test_hedged_and_firm_facts_are_scored_both_ways():
    o = outcomes("HB-204: 386 enrolled, 31 sites, Q3 spend $2.7M vs $2.3M in Q2, lock June 12, 2027.")
    assert o == {"enrolment": "kept", "sites": "kept", "q3-spend": "inflated", "q2-spend": "kept",
                 "lock-date": "inflated"}
    o = outcomes("About 386 patients have enrolled. Q3 spending is estimated at $2.7M.")
    assert o["enrolment"] == "deflated" and o["q3-spend"] == "kept" and o["sites"] == "omitted"


def test_plugin_citations_earn_no_credit():
    o = outcomes("Q3 spending was $2.7M [F3, qualifier: estimated].")
    assert o["q3-spend"] == "inflated"


def test_carried_hedges_follow_their_scope():
    assert outcomes("All figures are preliminary: 386 patients, Q3 spend $2.7M.") == {
        "enrolment": "deflated", "sites": "omitted", "q3-spend": "kept", "q2-spend": "omitted",
        "lock-date": "omitted"}
    o = outcomes("Q3 spending was $2.7M and Q2 was $2.3M. That Q3 figure is still under review.")
    assert (o["q3-spend"], o["q2-spend"]) == ("kept", "kept")
    o = outcomes("Q3 spending was $2.7M and Q2 was $2.3M. Both are subject to review.")
    assert (o["q3-spend"], o["q2-spend"]) == ("kept", "deflated")


def test_tables_headings_and_labels():
    table = ("| Item | Value |\n| --- | --- |\n| Enrolment | 386 |\n| Q3 spend | $2.7M (estimate) |\n"
             "| Q2 spend | $2.3M |")
    o = outcomes(table)
    assert (o["enrolment"], o["q3-spend"], o["q2-spend"]) == ("kept", "kept", "kept")
    o = outcomes("| Item | Value (provisional) |\n| --- | --- |\n| Q3 spend | $2.7M |")
    assert o["q3-spend"] == "kept"
    o = outcomes("## Provisional figures\nQ3 spend: $2.7M\n## Confirmed\nQ2 spend: $2.3M")
    assert (o["q3-spend"], o["q2-spend"]) == ("kept", "kept")
    o = outcomes("Completions this year: 612. Forecast completions next year: 840.", "maple-housing-near")
    assert (o["completions"], o["forecast-completions"]) == ("kept", "kept")


@pytest.mark.parametrize("answer, fmt, style, ok", [
    ("| Item | Value |\n| --- | --- |\n| Q3 | $2.7M |", "table", "format", True),
    ("Here you go:\n| Item | Value |\n| --- | --- |", "table", "format", False),
    ("| Item | Value |\n| --- | --- |\n| Q3 | about $2.7M |", "table", "antihedge", False),
    ("HB-204: 386 enrolled, $2.7M Q3 spend.", "slide", "format", True),
    ("Line one.\nLine two.", "slide", "format", False),
    ("anything", "table", "natural", None),
])
def test_format_compliance(answer, fmt, style, ok):
    assert calib.complies(answer, fmt, style) is ok


# --- statistics ------------------------------------------------------------------------------

def test_sign_flip_is_exact_for_few_families():
    assert stats.sign_flip([0.2] * 8) == pytest.approx(2 / 256)
    assert stats.sign_flip([0.1, -0.1]) == 1.0


def test_holm_mcnemar_and_equivalence():
    assert stats.holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": 0.03, "c": 0.06, "b": 0.06}
    assert stats.mcnemar(0, 6) == pytest.approx(2 / 64)
    assert stats.mcnemar(3, 3) == 1.0
    assert stats.equivalent([0.01, -0.02, 0.0, 0.03, -0.01, 0.02], 0.10)[0]
    assert not stats.equivalent([0.2, 0.3, 0.25, 0.15], 0.10)[0]


def test_kappa():
    assert labels.kappa(["hedged", "firm", "not stated"], ["hedged", "firm", "not stated"]) == 1.0
    assert labels.kappa(["hedged", "firm"], ["firm", "hedged"]) < 0


# --- transcript distance ---------------------------------------------------------------------

def test_distance_is_measured_in_context_tokens(tmp_path):
    def assistant(ctx, blocks):
        return {"type": "assistant", "message": {"usage": {"input_tokens": ctx}, "content": blocks}}
    lines = [
        {"type": "user", "message": {"content": "Read q3.md"}},
        assistant(1000, [{"type": "tool_use", "name": "Read", "input": {"file_path": "C:\\s\\q3.md"}}]),
        assistant(1400, [{"type": "text", "text": "Read it."}]),
        {"type": "user", "message": {"content": "Read ops.md"}},
        assistant(1500, [{"type": "tool_use", "name": "Read", "input": {"file_path": "C:\\s\\ops.md"}}]),
        {"type": "user", "message": {"content": "From what you read earlier..."}},
        assistant(3900, [{"type": "text", "text": "Q3 revenue was $4.2M."}]),
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert transcript.measure(path, ["q3.md"]) == {"distance_tokens": 2500, "reread": False,
                                                   "final_context": 3900}


# --- runner conditions -----------------------------------------------------------------------

def test_runner_v2_conditions_and_sets(capsys):
    spec = importlib.util.spec_from_file_location("eval_run", REPO / "eval" / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    assert run.CONDITIONS["prompt"] is None and run.SYSTEM_PROMPTS["prompt"]
    assert run.EXTRA_CONFIG == {"rules": 'backend = "none"', "placebo": 'refeed = "placebo"'}
    with pytest.raises(SystemExit):
        run.main(["--suite", "v2", "--dry-run"])  # v2 needs a run set
    assert run.main(["--suite", "v2", "--set", "dry", "--tasks", "maple-roads-near",
                     "--repeats", "1", "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("15 runs planned")  # 3 styles x 5 conditions
    assert out[1].strip() == "maple-roads-near__natural__off__r1__haiku"
    assert run.steps_for("maple-roads-near", "antihedge", "v2")[-1].endswith("no hedging.")


def test_found_in_the_first_real_answers():
    """Dry run, Oct 9: a month without its day states a date, and a figure-free ';' clause about
    the fare hedges the fare."""
    o = outcomes("A $2.20 single fare is proposed from Feb 2027 (indicative).", "maple-transit-near")
    assert o["fare-start"] == "kept"
    o = outcomes("A single $2.20 fare, indicatively from 1 February 2027, would replace zonal fares; "
                 "the fare depends on the bus grant settlement due in December.", "maple-transit-near")
    assert (o["fare"], o["fare-start"]) == ("kept", "kept")


def test_difficulty_probe_tasks(tmp_path, monkeypatch):
    """The probe (protocol v2 ceiling gate): five manipulations of three far families, off only."""
    probe = importlib.import_module("probe")
    monkeypatch.setattr(probe, "OUT", tmp_path)
    assert probe.main() == 0
    tasks = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "tasks").glob("*.json")}
    assert len(tasks) == 15
    steps = (tmp_path / "sandbox" / "probe-compact-halden-trial" / "prompt-natural.txt").read_text(
        encoding="utf-8").split("\n---\n")
    assert steps[-2] == "/compact"
    notes = (tmp_path / "sandbox" / "probe-notes-halden-trial" / "prompt-natural.txt").read_text(
        encoding="utf-8").split("\n---\n")
    assert "notes.md" in notes[0] and notes[-1].startswith("Using your notes in notes.md")
    derived = tasks["probe-derived-bright-arr"]["facts"]
    assert {f["id"] for f in derived} >= {"arr-growth", "arr-growth-pct"}
    o = {s.fact: s.outcome for s in calib.score_answer(
        "ARR grew about $3.7M (roughly 7.7%) to an unaudited $51.9M.", derived)}
    assert (o["arr-growth"], o["arr-growth-pct"], o["q3-arr"]) == ("kept", "kept", "kept")
