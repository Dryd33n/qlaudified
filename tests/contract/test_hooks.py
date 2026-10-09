"""Hook contract on recorded payloads: what goes in on stdin, what comes out, what lands in the store.

CAP-1, INJ-1..3, VER-1, REP-1, REP-4, NFR-7.
"""

import csv
import importlib.util
import io
import json
import sys

from qlaudified.store import Store


def test_read_payload_fills_the_store_and_stop_exports_csv(run_hook, payload, sandbox):
    post = payload("post_read")
    proc = run_hook("PostToolUse", post, project=sandbox)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    assert "[S2 q3-update.md L3] Q3 revenue is estimated at $4.2M" in out["additionalContext"]
    assert "source says: estimated, preliminary" in out["additionalContext"]
    assert "# Fernwick" not in out["additionalContext"]  # the heading has no fact to inject
    folder = sandbox / ".claude" / ".qlaudified" / "sessions" / "sim-session-0"
    assert [s.locator for s in Store(folder).spans()] == ["L1", "L3", "L4", "L5"]
    assert run_hook("PostToolUse", post, project=sandbox).stdout == b""  # nothing new: no delta

    stop = payload("stop")
    stop["session_id"] = post["session_id"]
    assert run_hook("Stop", stop, project=sandbox).returncode == 0
    with open(folder / "provenance.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[1]["source"] == "q3-update.md" and "estimated" in rows[1]["qualifiers"]
    timings = [json.loads(line) for line in (folder / "timings.jsonl").read_text().splitlines()]
    assert [t["event"] for t in timings] == ["PostToolUse", "PostToolUse", "Stop"]


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


def store_dir(sandbox):
    return sandbox / ".claude" / ".qlaudified" / "sessions" / "sim-session-0"


def same_session(post: dict, other: dict) -> dict:
    return {**other, "session_id": post["session_id"], "cwd": post["cwd"]}


def test_low_mode_captures_but_injects_and_verifies_nothing(run_hook, payload, sandbox):
    from qlaudified import config

    config.save_mode(sandbox, config.Mode.LOW)
    post = payload("post_read")
    assert run_hook("PostToolUse", post, project=sandbox).stdout == b""
    assert len(Store(store_dir(sandbox)).spans()) == 4
    stop = same_session(post, payload("stop"))
    assert run_hook("Stop", stop, project=sandbox).stdout == b""
    assert Store(store_dir(sandbox)).last_turn().answer.startswith("Ledger syncs")
    assert not (store_dir(sandbox) / "reports").exists()  # verified only on request


def test_subagent_delta_goes_to_the_subagent(run_hook, payload, sandbox):
    post = payload("post_read_subagent")
    proc = run_hook("PostToolUse", post, project=sandbox)
    context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "launch is tentatively scheduled for November 18, 2026" in context
    assert {s.agent_id for s in Store(store_dir(sandbox)).spans()} == {"a43f6aeb4f7a460ed"}


def test_compact_session_start_returns_the_digest(run_hook, payload, sandbox):
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    start = same_session(post, payload("session_start_compact"))
    out = json.loads(run_hook("SessionStart", start, project=sandbox).stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    assert "source says: estimated, preliminary" in out["additionalContext"]
    startup = same_session(post, payload("session_start_startup"))
    assert run_hook("SessionStart", startup, project=sandbox).stdout == b""


def test_stop_reports_a_dropped_qualifier(run_hook, payload, sandbox):
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    stop = same_session(post, payload("stop"))
    stop["last_assistant_message"] = "Q3 revenue was $4.2M. Headcount grew to 48."
    proc = run_hook("Stop", stop, project=sandbox)
    assert json.loads(proc.stdout) == {"systemMessage": (
        "qlaudified: 2 claims checked · 1 qualifier dropped (estimated) · 1 supported"
        " · /qlaudified report")}
    md = (store_dir(sandbox) / "reports" / "turn-1.md").read_text(encoding="utf-8")
    assert "**qualifier dropped** (rules): Q3 revenue was $4.2M." in md


def test_stop_without_sources_or_claims_leaves_no_store(run_hook, payload, sandbox):
    stop = payload("stop")
    stop["last_assistant_message"] = "done"
    assert run_hook("Stop", stop, project=sandbox).stdout == b""
    assert not (sandbox / ".claude").exists()


def test_message_display_adds_markers(run_hook, payload, sandbox):
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    shown = same_session(post, payload("message_display_partial"))
    shown["delta"] = "Q3 revenue was $4.2M.\n\n"
    out = json.loads(run_hook("MessageDisplay", shown, project=sandbox).stdout)["hookSpecificOutput"]
    assert out == {"hookEventName": "MessageDisplay",
                   "displayContent": "Q3 revenue was $4.2M [S2, qualifier: estimated, preliminary].\n\n"}
    shown["delta"] = "Nothing to cite.\n"
    assert run_hook("MessageDisplay", shown, project=sandbox).stdout == b""


def test_webfetch_refetches_the_page_and_stop_flags_the_summarys_dropped_hedge(
        run_hook, payload, sandbox, repo):
    from qlaudified.testing.webserver import serve

    server, site = serve(repo / "tests" / "fixtures" / "web")
    try:
        post = payload("post_webfetch")
        url = f"{site}/pricing.html"
        post["tool_input"]["url"] = url
        post["tool_response"].update(url=url, result="Pricing starts at $12 per seat per month.")
        assert run_hook("PostToolUse", post, project=sandbox, offline=False).returncode == 0
        stop = same_session(post, payload("stop"))
        stop["last_assistant_message"] = "Fernwick Ledger costs $12 per seat per month."
        proc = run_hook("Stop", stop, project=sandbox)  # waits for the detached re-fetch
    finally:
        server.shutdown()
    assert "qualifier dropped" in json.loads(proc.stdout)["systemMessage"]
    md = (store_dir(sandbox) / "reports" / "turn-1.md").read_text(encoding="utf-8")
    assert "**qualifier dropped** (rules): Fernwick Ledger costs $12" in md  # checked on the page
    assert "## WebFetch summaries that changed their page" in md
    assert "(dropped: subject to change, expected to)" in md
    assert not (sandbox / ".claude" / ".qlaudified" / "errors.log").exists()


def test_high_blocks_once_with_the_problems_then_lets_the_revision_stop(
        run_hook, payload, sandbox, monkeypatch):
    from qlaudified import config

    config.config_path(sandbox).parent.mkdir(parents=True, exist_ok=True)
    config.config_path(sandbox).write_text('mode = "high"\nbackend = "none"\n', encoding="utf-8")
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    stop = same_session(post, payload("stop"))
    stop["last_assistant_message"] = "Q3 revenue was $4.2M. Headcount grew to 48."
    out = json.loads(run_hook("Stop", stop, project=sandbox).stdout)
    assert out["decision"] == "block"
    assert out["reason"].splitlines()[1] == (
        '1. "Q3 revenue was $4.2M." drops the source\'s qualifier "estimated", "preliminary".')
    assert '[S2 q3-update.md L3] "Q3 revenue is estimated at $4.2M' in out["reason"]
    assert "Headcount" not in out["reason"]
    stop.update(stop_hook_active=True,
                last_assistant_message="Q3 revenue was an estimated $4.2M (preliminary).")
    out = json.loads(run_hook("Stop", stop, project=sandbox).stdout)
    assert "decision" not in out and out["systemMessage"].endswith("1 supported")
    assert Store(store_dir(sandbox)).last_turn().n == 1  # the revision replaced the same turn
    stop["last_assistant_message"] = "Q3 revenue was $4.2M."  # still wrong: never blocks twice
    assert "decision" not in json.loads(run_hook("Stop", stop, project=sandbox).stdout)


def test_high_post_tool_use_injects_earlier_sidecar_finds(run_hook, payload, sandbox):
    from qlaudified import config

    config.save_mode(sandbox, config.Mode.HIGH)
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)  # offline: the sidecar job isn't launched
    Store(store_dir(sandbox)).add_sidecar([{
        "span_id": "S3", "sentence": "Headcount grew to 48 by September 30, 2026.",
        "criticality": 0.8, "qualifiers": ["grew to"], "agent_id": "main"}])
    nxt = payload("post_read_subagent")
    nxt.update(session_id=post["session_id"], cwd=post["cwd"], agent_id=None)
    context = json.loads(run_hook("PostToolUse", nxt, project=sandbox).stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert context.splitlines()[0].startswith("[S3] source also qualifies: grew to")
    assert "launch is tentatively scheduled" in context and len(context) <= 600


def test_sidecar_only_drops_are_reported_but_never_block(run_hook, payload, sandbox):
    from qlaudified import config

    config.config_path(sandbox).parent.mkdir(parents=True, exist_ok=True)
    config.config_path(sandbox).write_text('mode = "high"\nbackend = "none"\n', encoding="utf-8")
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    Store(store_dir(sandbox)).add_sidecar([{
        "span_id": "S3", "sentence": "Headcount grew to 48 by September 30, 2026.",
        "criticality": 0.8, "qualifiers": ["grew to"], "agent_id": "main"}])
    stop = same_session(post, payload("stop"))
    stop["last_assistant_message"] = "Headcount reached 48 by September 30, 2026."
    out = json.loads(run_hook("Stop", stop, project=sandbox).stdout)
    assert "decision" not in out and "qualifier dropped (grew to)" in out["systemMessage"]
