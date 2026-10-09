"""/qlaudified mode and csv (MOD-1..3, REP-3)."""

import pytest

from qlaudified import cli, config
from qlaudified.store import Span, Store


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    return tmp_path


def test_mode_set_show_and_session_override(project, capsys):
    assert cli.main(["mode"]) == 0
    assert "medium (built-in default)" in capsys.readouterr().out
    cli.main(["mode", "high"])
    assert config.load(project).mode == "high"
    cli.main(["mode", "low", "--session"])
    assert config.load(project, "s1").mode == "low" and config.load(project).mode == "high"
    capsys.readouterr()
    cli.main(["mode"])
    assert "low (this session only)" in capsys.readouterr().out
    cli.main(["mode", "medium"])  # setting the default clears this session's override
    assert config.load(project, "s1").mode == "medium"


def test_csv_path_exports_this_session(project, capsys):
    assert cli.main(["csv", "--path"]) == 1
    folder = project / ".claude" / ".qlaudified" / "sessions" / "s1"
    Store(folder).add_span(Span("", "local-doc", "a.md", "L1", "text", hash="h"))
    capsys.readouterr()
    assert cli.main(["csv", "--path"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("provenance.csv") and (folder / "provenance.csv").exists()


def test_report_prints_the_last_turn_and_verifies_low_mode_turns_on_request(project, capsys):
    assert cli.main(["report"]) == 1
    folder = project / ".claude" / ".qlaudified" / "sessions" / "s1"
    store = Store(folder)
    store.add_span(Span("", "local-doc", "q3.md", "L3", "Q3 revenue is estimated at $4.2M.",
                        "4200000 USD", "estimated", hash="h"))
    store.start_turn("p1", "Q3 revenue was $4.2M.")  # as Stop records it in Low mode
    capsys.readouterr()
    assert cli.main(["report"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# qlaudified report · turn 1")
    assert "**qualifier dropped** (rules): Q3 revenue was $4.2M." in out
    assert (folder / "reports" / "turn-1.json").exists()
    config.config_path(project).write_text('backend = "none"\n', encoding="utf-8")
    assert cli.main(["report", "--deep"]) == 1
    assert 'backend = "none"' in capsys.readouterr().out


def test_report_deep_runs_one_llm_call_and_labels_its_verdicts(project, capsys, monkeypatch):
    from qlaudified import backends
    from qlaudified.backends.fake import FakeBackend

    folder = project / ".claude" / ".qlaudified" / "sessions" / "s1"
    store = Store(folder)
    store.add_span(Span("", "local-doc", "ops.md", "L2", "Deploys go out on Tuesdays after QA.",
                        hash="h"))
    store.start_turn("p1", "Releases ship weekly, after the testing team signs off at Fernwick.")
    fake = FakeBackend([{"verdicts": [{"id": "C1.1", "verdict": "inference", "span_ids": ["S1", "S9"],
                                       "dropped_qualifiers": [], "confidence": 0.7}]}])
    monkeypatch.setattr(backends, "get_backend", lambda name, model=None: fake)
    assert cli.main(["report", "--deep"]) == 0
    out = capsys.readouterr().out
    assert "**inference** (LLM): Releases ship weekly" in out
    assert len(fake.prompts) == 1 and "[S1] (ops.md L2)" in fake.prompts[0]
    assert Store(folder).claims("p1")[0].span_ids == ["S1"]  # S9 wasn't offered, so it's dropped
