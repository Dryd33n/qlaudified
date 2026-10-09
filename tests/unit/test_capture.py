"""Capture on the recorded payloads: facts and the sources-read log (CAP-1, CAP-5, CAP-6, PROV-1).

Design revision 2: only facts are stored (a sentence or line with a number, date or qualifier);
every passage read is logged as a source with a hash, never kept as text.
"""

import pytest

from qlaudified.capture import read_tool_result, spans_from_tool_result


def by_locator(spans):
    return {s.locator: s for s in spans}


def test_read_gives_one_fact_per_fact_line_and_logs_the_source(payload, sandbox):
    facts, sources = read_tool_result(payload("post_read"), sandbox)
    spans = by_locator(facts)
    assert set(spans) == {"L3", "L4", "L5"}  # the heading carries no fact
    revenue = spans["L3"]
    assert revenue.source == "q3-update.md" and revenue.origin == "local-doc"
    assert revenue.category == "Internal Document"
    assert revenue.numbers == "4200000 USD"
    assert revenue.qualifiers == "estimated; preliminary"
    assert spans["L4"].numbers == "48; 2026-09-30"
    assert revenue.turn and revenue.agent_id == "main" and len(revenue.hash) == 16
    assert {(s.source, s.rereadable) for s in sources} == {("q3-update.md", "file")}
    assert all(len(s.hash) == 16 for s in sources)


def test_a_file_named_in_the_prompt_is_a_provided_document(payload, sandbox):
    facts = spans_from_tool_result(payload("post_read"), sandbox, provided={"q3-update.md"})
    assert {f.category for f in facts} == {"Provided Document"}


def test_grep_lines_with_facts_become_facts(payload, sandbox):
    facts, sources = read_tool_result(payload("post_grep_content"), sandbox)
    assert [(s.source, s.locator) for s in facts] == [("ledger/config.py", "L6"),
                                                      ("ledger/sync.py", "L5")]
    assert all(s.origin == "code" for s in facts)
    assert len(sources) == 4  # every matching line was read; the "[Omitted ...]" entry is dropped


def test_cat_through_bash_is_upgraded_to_file_facts(payload, sandbox):
    facts = spans_from_tool_result(payload("post_bash"), sandbox)
    assert {s.source for s in facts} == {"ledger/config.py"}
    assert [s.locator for s in facts] == ["L1", "L3", "L4", "L5", "L6"]
    interval = by_locator(facts)["L5"]
    assert interval.text == "Roughly 15 minutes; may be lowered for paid plans."
    assert "roughly" in interval.qualifiers and "900 s" in interval.numbers


def test_other_commands_are_command_output_and_cant_be_reread(payload, sandbox):
    p = payload("post_bash")
    p["tool_input"]["command"] = "python -m pytest -q"
    p["tool_response"]["stdout"] = "33 passed in 2.47s"
    facts, sources = read_tool_result(p, sandbox)
    assert [(s.origin, s.source, s.locator, s.category) for s in facts] == [
        ("command-output", "$ python -m pytest -q", "p1", "Direct Retrieved Fact")]
    assert [s.rereadable for s in sources] == ["no"]


@pytest.mark.parametrize("command", ["pip install requests", "npm install", "py -3 -m pip install -e ."])
def test_install_output_is_skipped(payload, sandbox, command):
    p = payload("post_bash")
    p["tool_input"]["command"] = command
    assert read_tool_result(p, sandbox) == ([], [])


def test_powershell_get_content_counts_as_a_file_read(payload, sandbox):
    p = payload("post_bash")
    p["tool_name"] = "PowerShell"
    p["tool_input"]["command"] = 'Get-Content "ledger\\config.py"'
    assert {s.source for s in spans_from_tool_result(p, sandbox)} == {"ledger/config.py"}


def test_sed_range_sets_the_start_line(payload, sandbox):
    p = payload("post_bash")
    p["tool_input"]["command"] = "sed -n '5,6p' ledger/config.py"
    p["tool_response"]["stdout"] = "# Sync interval in seconds.\nSYNC_INTERVAL_S = 900"
    assert [s.locator for s in spans_from_tool_result(p, sandbox)] == ["L6"]


def test_webfetch_summary_facts_without_the_fetch_note(payload, sandbox):
    facts, sources = read_tool_result(payload("post_webfetch"), sandbox)
    assert facts and all(s.origin == "web-summary" for s in facts)
    assert all("WebFetch note" not in s.text for s in facts)
    assert [(s.locator, s.rereadable) for s in sources] == [("summary", "web")]


def test_websearch_titles_are_sources_not_facts(payload, sandbox):
    facts, sources = read_tool_result(payload("post_websearch"), sandbox)
    assert facts == []
    assert sources and all(s.origin == "search-snippet" and s.source.startswith("http")
                           for s in sources)


def test_mcp_list_response_is_logged(payload, sandbox):
    facts, sources = read_tool_result(payload("post_mcp"), sandbox)
    assert {s.source for s in sources} == {"mcp:claude_ai_Claude_Docs/guide"}
    assert all(s.origin == "mcp" and s.rereadable == "no" for s in sources)
    assert all(f.category == "Direct Retrieved Fact" for f in facts)


def test_subagent_facts_carry_the_agent_id(payload, sandbox):
    facts = spans_from_tool_result(payload("post_read_subagent"), sandbox)
    assert facts and {s.agent_id for s in facts} == {"a43f6aeb4f7a460ed"}


@pytest.mark.parametrize("name", ["post_glob", "post_toolsearch"])
def test_non_retrieval_tools_are_ignored(payload, sandbox, name):
    assert read_tool_result(payload(name), sandbox) == ([], [])


def test_the_store_never_captures_itself(payload, sandbox):
    p = payload("post_read")
    p["tool_response"]["file"]["filePath"] = str(sandbox / ".claude" / ".qlaudified" / "errors.log")
    assert read_tool_result(p, sandbox) == ([], [])


@pytest.mark.parametrize("response", [None, "text", [], {"file": None}, {"file": {"content": 3}}])
def test_odd_read_responses_give_nothing(payload, sandbox, response):
    p = payload("post_read")
    p["tool_response"] = response
    assert read_tool_result(p, sandbox) == ([], [])
