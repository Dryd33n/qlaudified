"""Handoff tooling (eval/v2/handoff_*.py): task build from the frozen gauntlet state and the scorer.
No live runs."""

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "eval" / "v2"
sys.path.insert(0, str(V2))

build = importlib.import_module("handoff_build")
score = importlib.import_module("handoff_score")
hops_score = importlib.import_module("hops_score")


def test_committed_tasks_match_the_builder(tmp_path, monkeypatch):
    out = tmp_path / "handoff"
    monkeypatch.setattr(build, "OUT", out)
    build.main([])
    committed = V2 / "handoff"
    for sub in ("sandbox", "tasks"):
        new = sorted(p.relative_to(out) for p in (out / sub).rglob("*") if p.is_file())
        assert new == sorted(p.relative_to(committed) for p in (committed / sub).rglob("*")
                             if p.is_file())
        for rel in new:
            assert (out / rel).read_bytes() == (committed / rel).read_bytes(), rel


def test_sandbox_keeps_the_sources_and_leaves_out_the_notes():
    for fam in build.FAMILIES:
        box = V2 / "handoff" / "sandbox" / f"handoff-{fam}"
        assert len(list((box / "abstracts").glob("*.md"))) == 120
        assert (box / "docs" / "report.md").exists() and not (box / "NOTES.md").exists()


def test_prompts_are_one_step_and_say_nothing_about_certainty():
    for fam in build.FAMILIES:
        box = V2 / "handoff" / "sandbox" / f"handoff-{fam}"
        report = (box / "docs" / "report.md").read_text(encoding="utf-8").strip()
        for variant in build.PROMPTS:
            text = (box / f"prompt-{variant}.txt").read_text(encoding="utf-8")
            assert "\n---\n" not in text  # the runner splits steps on it
            assert (report in text) == variant.startswith("paste")
            ask = text.replace(report, "")
            assert set(hops_score.cues(ask)) <= {"draft", "should", "expect"}  # the question's own words


def test_runner_sends_a_pasted_document_on_stdin(tmp_path, monkeypatch):
    """cmd.exe (shell=True on Windows) ends a command at a newline: the first handoff runs lost
    every flag after the pasted report's first line."""
    import json
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location("eval_run", REPO / "eval" / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    monkeypatch.setitem(run.TEST_ENV, "CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    calls = []

    def fake(cmd, **kw):
        calls.append((cmd, kw))
        out = {"session_id": "s1", "result": "ok", "total_cost_usd": 0.0, "num_turns": 1}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out).encode(), stderr=b"")

    monkeypatch.setattr(run.subprocess, "run", fake)
    run.run_one("handoff-fam-a", "paste-board", "off", "haiku", 15, tmp_path / "a", "handoff")
    run.run_one("handoff-fam-a", "edit-board", "off", "haiku", 15, tmp_path / "b", "handoff")
    (paste, paste_kw), (edit, edit_kw) = calls
    assert not any("\n" in arg for arg in paste) and paste_kw["input"].decode().count("\n") > 10
    assert "--output-format" in paste and paste_kw["stdin"] is None
    assert edit[2].startswith("Turn docs/report.md") and edit_kw["input"] is None


def test_opened_tells_abstracts_from_findings(tmp_path):
    use = '{"message": {"content": [{"type": "tool_use", '
    (tmp_path / "transcript.jsonl").write_text(
        use + '"name": "Read", "input": {"file_path": "data/findings.json"}}]}}\n'
        + use + '"name": "Bash", "input": {"command": "ls abstracts | wc -l"}}]}}\n')
    assert score.opened(tmp_path / "transcript.jsonl") == {"abstracts": False, "findings": True}
