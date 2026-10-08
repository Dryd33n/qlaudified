"""Capture on the recorded payloads in tests/fixtures/payloads (CAP-1, CAP-5, CAP-6)."""

import pytest

from qlaudified.capture import spans_from_tool_result


def by_locator(spans):
    return {s.locator: s for s in spans}


def test_read_gives_one_span_per_fact_line(payload, sandbox):
    spans = by_locator(spans_from_tool_result(payload("post_read"), sandbox))
    assert set(spans) == {"L1", "L3", "L4", "L5"}
    revenue = spans["L3"]
    assert revenue.source == "q3-update.md" and revenue.origin == "local-doc"
    assert revenue.numbers == "4200000 USD"
    assert revenue.qualifiers == "estimated; preliminary"
    assert spans["L4"].numbers == "48; 2026-09-30"
    assert revenue.turn and revenue.agent_id == "main" and len(revenue.hash) == 16


def test_grep_lines_become_line_spans(payload, sandbox):
    spans = spans_from_tool_result(payload("post_grep_content"), sandbox)
    assert [(s.source, s.locator) for s in spans] == [
        ("ledger/config.py", "L6"), ("ledger/sync.py", "L1"), ("ledger/sync.py", "L5"),
        ("ledger/sync.py", "L6"),
    ]  # the "[Omitted long matching line]" entry is dropped
    assert all(s.origin == "code" for s in spans)


def test_cat_through_bash_is_upgraded_to_a_file_span(payload, sandbox):
    spans = spans_from_tool_result(payload("post_bash"), sandbox)
    assert {s.source for s in spans} == {"ledger/config.py"}
    assert [s.locator for s in spans] == ["L1", "L3-L6"]
    assert "roughly" in spans[1].qualifiers and "900 s" in spans[1].numbers


def test_other_commands_are_command_output(payload, sandbox):
    p = payload("post_bash")
    p["tool_input"]["command"] = "python -m pytest -q"
    p["tool_response"]["stdout"] = "33 passed in 2.47s"
    spans = spans_from_tool_result(p, sandbox)
    assert [(s.origin, s.source, s.locator) for s in spans] == [
        ("command-output", "$ python -m pytest -q", "p1")]


@pytest.mark.parametrize("command", ["pip install requests", "npm install", "py -3 -m pip install -e ."])
def test_install_output_is_skipped(payload, sandbox, command):
    p = payload("post_bash")
    p["tool_input"]["command"] = command
    assert spans_from_tool_result(p, sandbox) == []


def test_powershell_get_content_counts_as_a_file_read(payload, sandbox):
    p = payload("post_bash")
    p["tool_name"] = "PowerShell"
    p["tool_input"]["command"] = 'Get-Content "ledger\\config.py"'
    assert {s.source for s in spans_from_tool_result(p, sandbox)} == {"ledger/config.py"}


def test_sed_range_sets_the_start_line(payload, sandbox):
    p = payload("post_bash")
    p["tool_input"]["command"] = "sed -n '5,6p' ledger/config.py"
    p["tool_response"]["stdout"] = "# Sync interval in seconds.\nSYNC_INTERVAL_S = 900"
    assert [s.locator for s in spans_from_tool_result(p, sandbox)] == ["L5-L6"]


def test_webfetch_summary_without_the_fetch_note(payload, sandbox):
    [span] = spans_from_tool_result(payload("post_webfetch"), sandbox)
    assert span.origin == "web-summary" and span.source.startswith("https://docs.python.org/")
    assert "WebFetch note" not in span.text and span.numbers == ""


def test_websearch_results_are_search_snippets(payload, sandbox):
    spans = spans_from_tool_result(payload("post_websearch"), sandbox)
    assert spans and all(s.origin == "search-snippet" and s.source.startswith("http") for s in spans)


def test_mcp_list_response(payload, sandbox):
    spans = spans_from_tool_result(payload("post_mcp"), sandbox)
    assert {s.source for s in spans} == {"mcp:claude_ai_Claude_Docs/guide"}
    assert all(s.origin == "mcp" for s in spans)


def test_subagent_spans_carry_the_agent_id(payload, sandbox):
    spans = spans_from_tool_result(payload("post_read_subagent"), sandbox)
    assert spans and {s.agent_id for s in spans} == {"a43f6aeb4f7a460ed"}


@pytest.mark.parametrize("name", ["post_glob", "post_toolsearch"])
def test_non_retrieval_tools_are_ignored(payload, sandbox, name):
    assert spans_from_tool_result(payload(name), sandbox) == []


def test_the_store_never_captures_itself(payload, sandbox):
    p = payload("post_read")
    p["tool_response"]["file"]["filePath"] = str(sandbox / ".claude" / ".qlaudified" / "errors.log")
    assert spans_from_tool_result(p, sandbox) == []


@pytest.mark.parametrize("response", [None, "text", [], {"file": None}, {"file": {"content": 3}}])
def test_odd_read_responses_give_no_spans(payload, sandbox, response):
    p = payload("post_read")
    p["tool_response"] = response
    assert spans_from_tool_result(p, sandbox) == []
