"""Hook contract on recorded payloads: what goes in on stdin, what comes out, what lands in the
ledger (design revision 2: INT-1..3, PROV-1, PROV-4, PROV-7, RFD-1..4, VER-1..4, REP-1, NFR-7).

All of these run offline: the sidecar backend is off, so rows carry their rule fields only. The
Administrator's judgment fields are tested in-process with a fake backend (test_administrator.py).
"""

import csv
import importlib.util
import io
import json
import os
import sys

from qlaudified import config
from qlaudified.store import Store


def store_dir(sandbox):
    return sandbox / ".claude" / ".qlaudified" / "sessions" / "sim-session-0"


def same_session(post: dict, other: dict) -> dict:
    return {**other, "session_id": post["session_id"], "cwd": post["cwd"]}


def csv_rows(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def set_mode(sandbox, mode: str) -> None:
    path = config.config_path(sandbox)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'mode = "{mode}"\nbackend = "none"\n', encoding="utf-8")


def test_read_fills_the_ledger_refeeds_new_facts_and_keeps_the_csv_current(run_hook, payload,
                                                                         sandbox):
    post = payload("post_read")
    proc = run_hook("PostToolUse", post, project=sandbox)
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    assert "[F1 q3-update.md L3] Q3 revenue is estimated at $4.2M" in out["additionalContext"]
    assert "source says: estimated, preliminary" in out["additionalContext"]
    folder = store_dir(sandbox)
    rows = csv_rows(folder / "provenance.csv")  # rewritten after the step, not at Stop
    assert [(r["fact_id"], r["locator"], r["origin"]) for r in rows] == [
        ("F1", "L3", "Internal Document"), ("F2", "L4", "Internal Document"),
        ("F3", "L5", "Internal Document")]
    assert rows[0]["source_qualifiers"] == "estimated; preliminary" and rows[0]["step"] == "1"
    assert not os.access(folder / "provenance.csv", os.W_OK)
    repeat = dict(post, tool_use_id="toolu_again")
    assert run_hook("PostToolUse", repeat, project=sandbox).stdout == b""  # nothing new

    stop = same_session(post, payload("stop"))
    stop["last_assistant_message"] = "Q3 revenue was $4.2M."
    assert run_hook("Stop", stop, project=sandbox).returncode == 0
    [claim] = csv_rows(folder / "claims.csv")
    assert (claim["verdict"], claim["fact_ids"]) == ("qualifier-dropped", "F1")
    revenue = csv_rows(folder / "provenance.csv")[0]
    assert revenue["first_use_qualifiers"] == "" and revenue["uses"].endswith(":final answer")
    timings = [json.loads(line) for line in (folder / "timings.jsonl").read_text().splitlines()]
    assert [t["event"] for t in timings] == ["PostToolUse", "PostToolUse", "Stop"]


def test_glob_with_no_ledger_is_never_stored(run_hook, payload, sandbox):
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


def test_low_records_everything_but_adds_nothing_to_claudes_context(run_hook, payload, sandbox):
    set_mode(sandbox, "low")
    post = payload("post_read")
    start = same_session(post, payload("session_start_startup"))
    assert run_hook("SessionStart", start, project=sandbox).stdout == b""
    assert run_hook("PostToolUse", post, project=sandbox).stdout == b""
    assert len(csv_rows(store_dir(sandbox) / "provenance.csv")) == 3  # the record is kept
    stop = same_session(post, payload("stop"))
    stop["last_assistant_message"] = "Q3 revenue was $4.2M."
    out = json.loads(run_hook("Stop", stop, project=sandbox).stdout)
    assert set(out) == {"systemMessage"}  # shown to the user, never to Claude; never blocks
    assert (store_dir(sandbox) / "reports" / "turn-1.md").exists()


def test_session_start_tells_claude_where_the_ledger_is(run_hook, payload, sandbox):
    start = payload("session_start_startup")
    out = json.loads(run_hook("SessionStart", start, project=sandbox).stdout)["hookSpecificOutput"]
    path = ".claude/.qlaudified/sessions/sim-session-0/provenance.csv"
    assert out["hookEventName"] == "SessionStart" and path in out["additionalContext"]
    assert "read-only" in out["additionalContext"]
    assert (sandbox / path).exists()  # the path exists from the start


def test_compact_session_start_returns_the_digest_and_the_path(run_hook, payload, sandbox):
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    start = same_session(post, payload("session_start_compact"))
    out = json.loads(run_hook("SessionStart", start, project=sandbox).stdout)["hookSpecificOutput"]
    assert "source says: estimated, preliminary" in out["additionalContext"]
    assert "provenance.csv" in out["additionalContext"].splitlines()[0]


def test_the_prompt_and_the_files_it_names_are_origins(run_hook, payload, sandbox):
    post = payload("post_read")
    prompt = {"session_id": post["session_id"], "cwd": post["cwd"], "prompt_id": "p1",
              "hook_event_name": "UserPromptSubmit",
              "prompt": "Read q3-update.md; our board wants roughly 50 seats by March 2027."}
    (sandbox / "q3-update.md").write_text("placeholder", encoding="utf-8")
    assert run_hook("UserPromptSubmit", prompt, project=sandbox).stdout == b""
    run_hook("PostToolUse", post, project=sandbox)
    rows = csv_rows(store_dir(sandbox) / "provenance.csv")
    assert ("User Prompt", "prompt") in {(r["origin"], r["source"]) for r in rows}
    read = [r for r in rows if r["source"] == "q3-update.md"]
    assert read and {r["origin"] for r in read} == {"Provided Document"}


def test_uses_in_claudes_reasoning_and_writes_are_tracked(run_hook, payload, sandbox, tmp_path):
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in [
        {"type": "user", "message": {"content": "write the notes"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text":
            "Revenue came in at $4.2M, so per head that's about $87.5K."}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_w"}]}},
    ]), encoding="utf-8")
    write = same_session(post, {
        "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_use_id": "toolu_w",
        "transcript_path": str(transcript), "prompt_id": post["prompt_id"],
        "tool_input": {"file_path": str(sandbox / "notes.md"),
                       "content": "- Q3 revenue: estimated $4.2M (preliminary)\n"},
        "tool_response": {"type": "create"}})
    assert run_hook("PostToolUse", write, project=sandbox).returncode == 0
    rows = {r["fact_id"]: r for r in csv_rows(store_dir(sandbox) / "provenance.csv")}
    revenue = rows["F1"]
    assert revenue["first_use_step"] == "2" and revenue["first_use_qualifiers"] == ""  # dropped
    assert revenue["uses"] == "2:reasoning; 2:Write notes.md"
    [own] = [r for r in rows.values() if r["read_as"] == "claude"]
    assert own["claim"] == "Revenue came in at $4.2M, so per head that's about $87.5K."
    assert own["origin"] == "Unclassified" and own["locator"] == "step 2"  # sidecar off


def test_reads_of_the_ledger_are_consults_not_sources(run_hook, payload, sandbox):
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    folder = store_dir(sandbox)
    consult = dict(post, tool_use_id="toolu_c")
    consult["tool_input"] = {"file_path": str(folder / "provenance.csv")}
    consult["tool_response"] = {"type": "text", "file": {
        "filePath": str(folder / "provenance.csv"), "content": "fact_id,claim\nF1,x\n"}}
    assert run_hook("PostToolUse", consult, project=sandbox).stdout == b""
    [line] = (folder / "consults.jsonl").read_text().splitlines()
    assert json.loads(line)["step"] == 2 and len(csv_rows(folder / "provenance.csv")) == 3


def test_subagent_delta_goes_to_the_subagent(run_hook, payload, sandbox):
    post = payload("post_read_subagent")
    context = json.loads(run_hook("PostToolUse", post, project=sandbox).stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert "launch is tentatively scheduled for November 18, 2026" in context
    assert {s.agent_id for s in Store(store_dir(sandbox)).spans()} == {"a43f6aeb4f7a460ed"}


def test_stop_reports_a_dropped_qualifier(run_hook, payload, sandbox):
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    stop = same_session(post, payload("stop"))
    stop["last_assistant_message"] = "Q3 revenue was $4.2M. Headcount grew to 48."
    assert json.loads(run_hook("Stop", stop, project=sandbox).stdout) == {"systemMessage": (
        "qlaudified: 2 claims checked · 1 qualifier dropped (estimated) · 1 supported"
        " · /qlaudified report")}
    md = (store_dir(sandbox) / "reports" / "turn-1.md").read_text(encoding="utf-8")
    assert "**qualifier dropped** (rules): Q3 revenue was $4.2M." in md
    assert "## Provenance ledger: facts used" in md


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
                   "displayContent": "Q3 revenue was $4.2M [F1, qualifier: estimated, preliminary].\n\n"}
    shown["delta"] = "Nothing to cite.\n"
    assert run_hook("MessageDisplay", shown, project=sandbox).stdout == b""


def test_webfetch_refetches_the_page_and_stop_flags_the_summarys_dropped_hedge(
        run_hook, payload, sandbox, repo):
    from qlaudified.testing.webserver import serve

    set_mode(sandbox, "medium")  # backend "none": online for the re-fetch, but no model calls
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
        run_hook, payload, sandbox):
    set_mode(sandbox, "high")
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    stop = same_session(post, payload("stop"))
    stop["last_assistant_message"] = "Q3 revenue was $4.2M. Headcount grew to 48."
    out = json.loads(run_hook("Stop", stop, project=sandbox).stdout)
    assert out["decision"] == "block"
    assert out["reason"].splitlines()[1] == (
        '1. "Q3 revenue was $4.2M." drops the source\'s qualifier "estimated", "preliminary".')
    assert '[F1 q3-update.md L3] "Q3 revenue is estimated at $4.2M' in out["reason"]
    assert "Headcount" not in out["reason"]
    stop.update(stop_hook_active=True,
                last_assistant_message="Q3 revenue was an estimated $4.2M (preliminary).")
    out = json.loads(run_hook("Stop", stop, project=sandbox).stdout)
    assert "decision" not in out and out["systemMessage"].endswith("1 supported")
    assert Store(store_dir(sandbox)).last_turn().n == 1  # the revision replaced the same turn
    stop["last_assistant_message"] = "Q3 revenue was $4.2M."  # still wrong: never blocks twice
    assert "decision" not in json.loads(run_hook("Stop", stop, project=sandbox).stdout)


def test_sidecar_only_qualifiers_are_reported_but_never_block(run_hook, payload, sandbox):
    set_mode(sandbox, "high")
    post = payload("post_read")
    run_hook("PostToolUse", post, project=sandbox)
    store = Store(store_dir(sandbox))
    store.update_fact("F2", qualifiers="grew to")  # as if the sidecar had added it
    stop = same_session(post, payload("stop"))
    stop["last_assistant_message"] = "Headcount reached 48 by September 30, 2026."
    out = json.loads(run_hook("Stop", stop, project=sandbox).stdout)
    assert "decision" not in out and "qualifier dropped (grew to)" in out["systemMessage"]
