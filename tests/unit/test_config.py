"""Config loading, saved mode and one-session override (MOD-1..3, CFG-2)."""

from qlaudified import config
from qlaudified.config import Mode


def test_defaults_without_a_file(tmp_path):
    cfg = config.load(tmp_path)
    assert cfg.mode == Mode.MEDIUM and cfg.mode_source == "default"
    assert cfg.inject_budget_chars == 600 and cfg.backend_model == "haiku"
    assert cfg.problems == []


def test_save_mode_persists_and_keeps_other_settings(tmp_path):
    config.save_mode(tmp_path, Mode.HIGH)
    path = config.config_path(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("600", "900"), encoding="utf-8")
    config.save_mode(tmp_path, Mode.LOW)
    cfg = config.load(tmp_path)
    assert cfg.mode == Mode.LOW and cfg.mode_source == "config"
    assert cfg.inject_budget_chars == 900


def test_mode_writes_create_the_store_gitignore(tmp_path):
    config.save_mode(tmp_path, Mode.HIGH)
    gitignore = config.store_dir(tmp_path) / ".gitignore"
    assert gitignore.exists()
    gitignore.unlink()
    config.set_session_mode(tmp_path, "s1", Mode.LOW)
    assert gitignore.exists()


def test_session_override_leaves_the_default_alone(tmp_path):
    config.save_mode(tmp_path, Mode.MEDIUM)
    config.set_session_mode(tmp_path, "s1", Mode.HIGH)
    assert config.load(tmp_path, "s1").mode == Mode.HIGH
    assert config.load(tmp_path, "s1").mode_source == "session"
    assert config.load(tmp_path, "s2").mode == Mode.MEDIUM
    assert config.load(tmp_path).mode == Mode.MEDIUM
    config.set_session_mode(tmp_path, "s1", None)
    assert config.load(tmp_path, "s1").mode == Mode.MEDIUM


def test_broken_file_gives_defaults_and_a_problem(tmp_path):
    path = config.config_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('mode = "high\n[[[', encoding="utf-8")
    cfg = config.load(tmp_path)
    assert cfg.mode == Mode.MEDIUM and len(cfg.problems) == 1


def test_bad_values_are_reported_not_applied(tmp_path):
    path = config.config_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('mode = "extreme"\ninject_budget_chars = "lots"\nretention_days = true\n',
                    encoding="utf-8")
    cfg = config.load(tmp_path)
    assert cfg.mode == Mode.MEDIUM and cfg.inject_budget_chars == 600 and cfg.retention_days == 30
    assert len(cfg.problems) == 3


def test_extra_hedges_reach_the_lexicon(tmp_path):
    path = config.config_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('[hedges]\nestimate = ["ballpark"]\n', encoding="utf-8")
    assert "ballpark" in config.load(tmp_path).lexicon()["estimate"]
