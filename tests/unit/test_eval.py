"""Eval tooling (eval/run.py, eval/handoff/): prompts, sandboxes, scorer and runner. No live runs."""

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
HANDOFF = REPO / "eval" / "handoff"
sys.path.insert(0, str(HANDOFF))

build = importlib.import_module("build")
score = importlib.import_module("score")
cues = importlib.import_module("cues")
TASKS = sorted(p.stem for p in (HANDOFF / "tasks").glob("*.json"))


def _run_module():
    spec = importlib.util.spec_from_file_location("eval_run", REPO / "eval" / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    return run


def _task(name: str) -> dict:
    return json.loads((HANDOFF / "tasks" / f"{name}.json").read_text(encoding="utf-8"))


def test_committed_prompts_match_the_builder(tmp_path, monkeypatch):
    for name in TASKS:
        box = tmp_path / name
        (box / "docs").mkdir(parents=True)
        (box / "docs" / "report.md").write_bytes(
            (HANDOFF / "sandbox" / name / "docs" / "report.md").read_bytes())
    monkeypatch.setattr(build, "SANDBOX", tmp_path)
    build.main()
    for name in TASKS:
        for variant in build.PROMPTS:
            rel = Path(name) / f"prompt-{variant}.txt"
            assert (tmp_path / rel).read_bytes() == (HANDOFF / "sandbox" / rel).read_bytes(), rel


def test_sandbox_keeps_the_sources_and_the_labels_match_them():
    assert TASKS == ["handoff-fam-a", "handoff-fam-b"]
    kinds = {}
    for name in TASKS:
        box = HANDOFF / "sandbox" / name
        task = _task(name)
        assert (box / "docs" / "report.md").exists() and not (box / "NOTES.md").exists()
        assert sorted(i["kind"] for i in task["interventions"] if i["focus"]) == \
            ["firm"] * 3 + ["hedged"] * 3
        for study in task["studies"]:
            text = (box / "abstracts" / f"{study['id']}.md").read_text(encoding="utf-8")
            results = next(line for line in text.splitlines() if line.startswith("Results:"))
            assert bool(cues.find(results)) == (study["kind"] == "hedged"), study["id"]
        kinds[name] = {i["name"]: i["kind"] for i in task["interventions"]}
    a, b = kinds.values()
    assert all(a[n] != b[n] for n in a)  # the families swap hedged and firm


def test_prompts_are_one_step_and_say_nothing_about_certainty():
    for name in TASKS:
        box = HANDOFF / "sandbox" / name
        report = (box / "docs" / "report.md").read_text(encoding="utf-8").strip()
        for variant in build.PROMPTS:
            text = (box / f"prompt-{variant}.txt").read_text(encoding="utf-8")
            assert "\n---\n" not in text  # the runner splits steps on it
            assert (report in text) == variant.startswith("paste")
            ask = text.replace(report, "")
            assert set(cues.find(ask)) <= {"draft", "should", "expect"}  # the question's own words


def test_cues_mask_the_month_and_about_meaning_concerning():
    assert cues.find("Yoga may have reduced fatigue by about 30%.") == ["may", "about"]
    assert cues.find("Published 17 May; an update about the trial.") == []


def test_stretches_and_outcomes():
    segs = score.stretches("- **Yoga:** may cut fatigue 36%.\n- **Tai chi:** cut falls by 20%.",
                           ["Yoga", "Tai chi"])
    assert score.outcome("hedged", segs["Yoga"]) == "kept"
    assert score.outcome("firm", segs["Tai chi"]) == "plain"
    assert score.outcome("hedged", "Yoga 36%") == "omitted"
    assert score.outcome("hedged", None) == "omitted"


def test_access_tells_reading_an_abstract_from_listing_the_folder():
    def bash(command):
        return {"name": "Bash", "input": {"command": command}}

    assert score.abstract_access(bash("ls abstracts | wc -l")) == "listed"
    assert score.abstract_access(bash('grep -l "Yoga" abstracts/*.md | wc -l')) == "listed"
    # seen in a run: a count, then a cat of one abstract, in one command
    assert score.abstract_access(bash('grep -l "x" abstracts/*.md | wc -l && cat abstracts/A001.md')) == "read"
    assert score.abstract_access(bash("ls abstracts | head; cat focus.txt")) == "listed"
    assert score.abstract_access(bash('grep -h "Results" abstracts/*.md | head -60')) == "read"
    assert score.abstract_access({"name": "Read", "input": {"file_path": "C:\\t\\abstracts\\A1.md"}}) == "read"
    assert score.abstract_access({"name": "Grep", "input": {"path": "abstracts",
                                                            "output_mode": "count"}}) == "listed"
    assert score.abstract_access(bash("cat data/findings.json")) is None


def test_opened_tells_abstracts_from_findings(tmp_path):
    use = '{"message": {"content": [{"type": "tool_use", '
    (tmp_path / "transcript.jsonl").write_text(
        use + '"name": "Read", "input": {"file_path": "data/findings.json"}}]}}\n'
        + use + '"name": "Bash", "input": {"command": "ls abstracts | wc -l"}}]}}\n')
    assert score.opened(tmp_path / "transcript.jsonl") == {"abstracts": False, "findings": True}


def test_score_run_reads_the_answer_and_the_transcript(tmp_path):
    task = _task("handoff-fam-a")
    hedged = [i["name"] for i in task["interventions"] if i["focus"] and i["kind"] == "hedged"]
    answer = "\n".join(f"- **{n}:** reduces it by 30% at $40 per patient." for n in hedged)
    (tmp_path / "result.json").write_text(json.dumps(
        {"task": "handoff-fam-a", "variant": "paste-board", "condition": "off", "result": answer}))
    run = score.score_run(tmp_path, task)
    assert run["cells"].count(("hedged", "inflated")) == 3
    assert run["cells"].count(("firm", "omitted")) == 3 and not run["abstracts"]


def test_runner_plans_and_sends_a_pasted_report_on_stdin(tmp_path, monkeypatch, capsys):
    """cmd.exe (shell=True on Windows) ends a command at a newline: pasted reports go on stdin."""
    run = _run_module()
    assert run.main(["--set", "dry", "--repeats", "1", "--dry-run"]) == 0
    assert capsys.readouterr().out.startswith("8 runs planned")
    monkeypatch.setitem(run.TEST_ENV, "CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    calls = []

    def fake(cmd, **kw):
        calls.append((cmd, kw))
        out = {"session_id": "s1", "result": "ok", "total_cost_usd": 0.0, "num_turns": 1}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out).encode(), stderr=b"")

    monkeypatch.setattr(run.subprocess, "run", fake)
    run.run_one("handoff-fam-a", "paste-board", "off", "haiku", 15, tmp_path / "a")
    run.run_one("handoff-fam-a", "edit-board", "medium", "haiku", 15, tmp_path / "b")
    (paste, paste_kw), (edit, edit_kw) = calls
    assert not any("\n" in arg for arg in paste) and paste_kw["input"].decode().count("\n") > 10
    assert "--output-format" in paste and paste_kw["stdin"] is None
    assert edit[2].startswith("Turn docs/report.md") and edit_kw["input"] is None
    assert "--plugin-dir" in edit and "--plugin-dir" not in paste
    tools = paste[paste.index("--allowedTools") + 1].split(",")
    assert "PowerShell" in tools and "Bash" in tools  # a denied PowerShell call once lost a step


def test_eval_imports_nothing_from_the_plugin():
    for path in [REPO / "eval" / "run.py", *HANDOFF.glob("*.py")]:
        source = path.read_text(encoding="utf-8")
        assert "from qlaudified" not in source and "import qlaudified" not in source, path
