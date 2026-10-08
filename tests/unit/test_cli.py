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
