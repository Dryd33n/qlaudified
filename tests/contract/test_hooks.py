"""Hook contract on recorded payloads: what goes in on stdin, what lands in the store (CAP-1, NFR-7)."""

import csv
import importlib.util
import io
import json
import sys

from qlaudified.store import Store


def test_read_payload_fills_the_store_and_stop_exports_csv(run_hook, payload, sandbox):
    post = payload("post_read")
    proc = run_hook("PostToolUse", post, project=sandbox)
    assert proc.returncode == 0 and proc.stdout == b""  # Sprint 1 injects nothing
    folder = sandbox / ".claude" / ".qlaudified" / "sessions" / "sim-session-0"
    assert [s.locator for s in Store(folder).spans()] == ["L1", "L3", "L4", "L5"]

    stop = payload("stop")
    stop["session_id"] = post["session_id"]
    assert run_hook("Stop", stop, project=sandbox).returncode == 0
    with open(folder / "provenance.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[1]["source"] == "q3-update.md" and "estimated" in rows[1]["qualifiers"]
    timings = [json.loads(line) for line in (folder / "timings.jsonl").read_text().splitlines()]
    assert [t["event"] for t in timings] == ["PostToolUse", "Stop"]


def test_glob_is_never_stored(run_hook, payload, sandbox):
    assert run_hook("PostToolUse", payload("post_glob"), project=sandbox).returncode == 0
    assert not (sandbox / ".claude" / ".qlaudified" / "sessions").exists()


def test_malformed_and_empty_payloads_exit_zero_quietly(run_hook, repo, sandbox):
    for name in ("malformed.txt", "empty.txt"):
        raw = (repo / "tests" / "fixtures" / "payloads" / name).read_text(encoding="utf-8")
        proc = run_hook("PostToolUse", raw, project=sandbox)
        assert proc.returncode == 0 and proc.stdout == b""


def load_run_py(repo):
    spec = importlib.util.spec_from_file_location("qlaudified_run", repo / "hooks" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_in_process(run_py, monkeypatch, event, payload, capsys):
    monkeypatch.setattr(sys, "argv", ["run.py", event])
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))
    assert run_py.main() == 0
    return capsys.readouterr().out


def test_a_crashing_handler_is_logged_once_and_exits_zero(repo, monkeypatch, capsys, sandbox):
    run_py = load_run_py(repo)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(sandbox))
    import qlaudified.hooks.post_tool_use as handler

    def boom(payload):
        raise RuntimeError("forced")

    monkeypatch.setattr(handler, "handle", boom)
    out = run_in_process(run_py, monkeypatch, "PostToolUse", {"session_id": "s1"}, capsys)
    assert out == ""
    lines = (sandbox / ".claude" / ".qlaudified" / "errors.log").read_text().splitlines()
    assert len(lines) == 1 and "forced" in json.loads(lines[0])["traceback"]


def test_old_python_warns_at_session_start_and_logs_once(repo, monkeypatch, capsys, sandbox):
    run_py = load_run_py(repo)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(sandbox))
    monkeypatch.setattr(run_py, "MIN_PYTHON", (99, 0))
    out = run_in_process(run_py, monkeypatch, "SessionStart", {"session_id": "s1"}, capsys)
    assert "needs Python 99.0+" in json.loads(out)["systemMessage"]
    assert run_in_process(run_py, monkeypatch, "PostToolUse", {"session_id": "s1"}, capsys) == ""
    run_in_process(run_py, monkeypatch, "SessionStart", {"session_id": "s1"}, capsys)
    assert len((sandbox / ".claude" / ".qlaudified" / "errors.log").read_text().splitlines()) == 1
