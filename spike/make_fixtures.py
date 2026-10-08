"""Extract one hook payload per case from tests/sessions/ into tests/fixtures/payloads/. Python 3.7+.

    py -3 spike/make_fixtures.py [--force]

Each fixture is exactly what Claude Code sent on the hook's stdin (the probe's `payload`), already
scrubbed by spike/collect.py: paths use <HOME> and <SANDBOX>, session IDs use <SESSION_n>. Tests
substitute <SANDBOX> with a temp folder. The MCP fixture is hand-built from the shape recorded in
docs/findings/sprint-0.md, because that session wasn't collected.
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
SESSIONS = os.path.join(REPO, "tests", "sessions")
OUT = os.path.join(REPO, "tests", "fixtures", "payloads")


def tool(name, sub=None):
    def match(event, p):
        return (event == "PostToolUse" and p.get("tool_name") == name
                and (sub is None or ("agent_id" in p) == sub))
    return match


def event_is(name, **fields):
    def match(event, p):
        return event == name and all(p.get(k) == v for k, v in fields.items())
    return match


# name -> (session, matcher, what the case covers)
CASES = {
    "post_read": ("notes-windows", tool("Read"), "CAP-1: file text in tool_response.file, no line prefixes"),
    "post_grep_content": ("repo-windows", tool("Grep"), "CAP-1: rel\\path:line:text lines; numFiles 0"),
    "post_bash": ("repo-windows", tool("Bash"), "CAP-1: stdout/stderr only; source from the command"),
    "post_webfetch": ("web-windows", tool("WebFetch"), "CAP-3: summary in result, raw size in bytes"),
    "post_websearch": ("web-windows", tool("WebSearch"), "CAP-5: {title, url} results"),
    "post_glob": ("inject-windows", tool("Glob"), "ignored tool: capture must skip it"),
    "post_toolsearch": ("web-windows", tool("ToolSearch"), "ignored tool: capture must skip it"),
    "post_read_subagent": ("interactive-windows", tool("Read", sub=True), "CAP-6: agent_id and agent_type present"),
    "session_start_startup": ("notes-windows", event_is("SessionStart", source="startup"), "startup"),
    "session_start_compact": ("interactive-windows", event_is("SessionStart", source="compact"), "INJ-3: after /compact"),
    "pre_compact": ("interactive-windows", event_is("PreCompact"), "trigger: manual"),
    "stop": ("repo-windows", event_is("Stop"), "VER-1: last_assistant_message, stop_hook_active"),
    "subagent_stop_internal": ("interactive-windows", event_is("SubagentStop", agent_type=""), "helper agent: must be ignored"),
    "subagent_stop_explore": ("interactive-windows", event_is("SubagentStop", agent_type="Explore"), "real subagent"),
    "message_display_partial": ("interactive-windows", event_is("MessageDisplay", final=False), "REP-1: one paragraph, not final"),
    "message_display_final": ("interactive-windows", event_is("MessageDisplay", final=True), "REP-1: last delta"),
    "user_prompt_submit": ("notes-windows", event_is("UserPromptSubmit"), "prompt_id keys the turn"),
}

MCP_FIXTURE = {
    "session_id": "<SESSION_0>",
    "transcript_path": "<HOME>\\.claude\\projects\\<SANDBOX>\\<SESSION_0>.jsonl",
    "cwd": "<SANDBOX>",
    "prompt_id": "00000000-0000-0000-0000-000000000000",
    "permission_mode": "default",
    "effort": {"level": "medium"},
    "hook_event_name": "PostToolUse",
    "tool_name": "mcp__claude_ai_Claude_Docs__guide",
    "tool_input": {"items": ["topic.index"]},
    "tool_response": [{"type": "text", "text": "# topic.index\n\nDocs are living documents: a doc holds tabs, each tab holds prose, tables, charts and chips."}],
    "tool_use_id": "toolu_00000000000000000000mcp",
    "duration_ms": 412,
}


def first_payload(session, match):
    path = os.path.join(SESSIONS, session, "events.jsonl")
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            p = r.get("payload") or {}
            if match(r["event"], p):
                return p
    raise SystemExit("no match for a case in %s" % session)


def write(name, text, force):
    path = os.path.join(OUT, name)
    if os.path.exists(path) and not force:
        raise SystemExit("refusing to overwrite %s (use --force)" % path)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not os.path.isdir(OUT):
        os.makedirs(OUT)

    rows = []
    for name, (session, match, note) in CASES.items():
        payload = first_payload(session, match)
        write(name + ".json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n", args.force)
        rows.append((name + ".json", session, note))
    write("post_mcp.json", json.dumps(MCP_FIXTURE, indent=2) + "\n", args.force)
    rows.append(("post_mcp.json", "synthetic", "CAP-1: MCP response is a list of {type, text} blocks"))
    write("malformed.txt", '{"session_id": "x", "tool_name": "Read", "tool_input": {"file_path": "C:\\Users\\x"}}\n', args.force)
    rows.append(("malformed.txt", "synthetic", "NFR-7: invalid JSON (bad \\U escape); hook logs and exits 0"))
    write("empty.txt", "", args.force)
    rows.append(("empty.txt", "synthetic", "NFR-7: empty stdin"))

    lines = ["# Hook payload fixtures", "",
             "One payload per case, exactly as Claude Code sent it on stdin (2.1.294, Windows).",
             "Generated by `spike/make_fixtures.py` from `tests/sessions/`; paths use `<HOME>` and",
             "`<SANDBOX>` placeholders (tests swap `<SANDBOX>` for a temp folder).", "",
             "| File | From | Covers |", "| --- | --- | --- |"]
    lines += ["| `%s` | %s | %s |" % r for r in rows]
    write("README.md", "\n".join(lines) + "\n", args.force)
    print("wrote %d fixtures to %s" % (len(rows), OUT))


if __name__ == "__main__":
    main()
