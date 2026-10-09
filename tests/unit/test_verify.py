"""BM25 candidates, Tier 1 and final labels on the seed sandboxes (VER-1..3)."""

from pathlib import Path

import pytest

from qlaudified.config import Config
from qlaudified.store import Span, Turn
from qlaudified.testing.spans import spans_from_files
from qlaudified.verify import verify_answer
from qlaudified.verify.candidates import Index
from qlaudified.verify.tier1 import check

SANDBOX = Path(__file__).resolve().parents[1] / "sandbox"


def spans_from(task: str, *files: str) -> list[Span]:
    return spans_from_files(SANDBOX / task, *files)


@pytest.fixture
def notes():
    return spans_from("notes", "q3-update.md", "launch-memo.md")


def at(spans, locator, source="q3-update.md"):
    return next(s.span_id for s in spans if s.locator == locator and s.source == source)


def verdicts(answer: str, spans) -> list[tuple[str, str, list[str]]]:
    claims, _ = verify_answer(answer, spans, Turn(1, "p1", answer, ""), Config())
    return [(c.text, c.verdict, c.dropped_qualifiers) for c in claims]


def test_bm25_ranks_the_fact_line_first_and_honors_cited_ids(notes):
    index = Index(notes)
    assert index.top("What was Q3 revenue?")[0][0].span_id == at(notes, "L3")
    assert index.top("Headcount reached 48")[0][0].span_id == at(notes, "L4")
    assert index.top("Pricing per seat [F5]")[0][0].span_id == "F5"


def test_dropped_qualifier_is_flagged_with_the_words(notes):
    assert verdicts("Q3 revenue was $4.2M.", notes) == [
        ("Q3 revenue was $4.2M.", "qualifier-dropped", ["estimated", "preliminary"])]


def test_kept_qualifier_and_a_same_class_paraphrase_are_supported(notes):
    assert verdicts("Q3 revenue is estimated at $4.2M.", notes)[0][1] == "supported"
    assert verdicts("Q3 revenue was about 4.2 million USD.", notes)[0][1] == "supported"


def test_strongest_class_decides(notes):
    # Source: "may open in early 2027, pending the lease review" -> tentative beats modal.
    assert verdicts("The Lisbon office may open in 2027.", notes)[0][1:] == (
        "qualifier-dropped", ["pending"])
    assert verdicts("The Lisbon office may open in 2027, pending a lease review.", notes)[0][1] == (
        "supported")


def test_wrong_number_on_the_same_topic_is_contradicted(notes):
    assert verdicts("Headcount grew to 52 by September 30, 2026.", notes)[0][1] == "contradicted"
    assert verdicts("Q3 revenue was an estimated $5.1M.", notes)[0][1] == "contradicted"


def test_unknown_number_is_unsupported(notes):
    assert verdicts("Q4 revenue was $6.3M.", notes)[0][1] in ("unsupported", "contradicted")
    assert verdicts("The Berlin office employs 300 engineers.", notes)[0][1] == "unsupported"


def test_hedges_belong_to_their_own_line_in_code():
    spans = spans_from("repo", "ledger/config.py", "ledger/sync.py")
    # The comment says "Roughly 15 minutes", but the value line itself is unhedged.
    assert check("SYNC_INTERVAL_S is 900", spans)["verdict"] == "supported"
    result = check("Ledger syncs every 15 minutes, but retries can run sooner.", spans)
    assert result["verdict"] in ("supported", "qualifier-dropped")


def test_claims_without_numbers_use_word_overlap():
    spans = spans_from("repo", "ledger/sync.py")
    assert check("Retries may run sooner.", spans)["verdict"] == "supported"
    assert check("Retries run sooner.", spans)["verdict"] == "qualifier-dropped"
    assert check("The billing service uses Stripe webhooks.", spans) is None


def test_non_critical_claims_are_skipped_in_medium(notes):
    claims, skipped = verify_answer(
        "This matters for decisions. Q3 revenue was $4.2M.", notes, Turn(2, "p2", "", ""), Config())
    assert skipped == 1 and [c.claim_id for c in claims] == ["C2.1"]


def test_a_hedge_later_in_the_sentence_still_qualifies_an_earlier_clause():
    # Live, Sprint 2: splitting at ", but" separated the price from "subject to change".
    spans = spans_from("seed-compaction", "pricing.md")
    answer = ("Seat pricing is expected to start at $12 per seat per month, but that is subject to "
              "change after the beta.")
    assert [v for _, v, _ in verdicts(answer, spans)] == ["supported", "supported"]


def test_a_date_without_a_year_matches_the_same_day():
    spans = spans_from("seed-conflict", "launch-plan-v1.md")
    assert check("The older plan tentatively said November 18.", spans)["verdict"] == "supported"


def test_claims_without_facts_are_checked_by_re_reading_sources(tmp_path):
    """Design revision 2: only facts are stored, so a claim with no number or qualifier is
    checked against the files Claude read, re-read from disk (VER-3)."""
    import shutil

    from qlaudified import capture
    from qlaudified.store import Store
    from qlaudified.verify import verify_turn

    project = tmp_path / "project"
    shutil.copytree(SANDBOX / "repo", project)
    store = Store(project / ".claude" / ".qlaudified" / "sessions" / "s1")
    content = (project / "ledger" / "sync.py").read_text(encoding="utf-8")
    payload = {"tool_name": "Read", "cwd": str(project),
               "tool_response": {"file": {"filePath": str(project / "ledger" / "sync.py"),
                                          "content": content, "startLine": 1}}}
    facts, sources = capture.read_tool_result(payload, project)
    store.add_spans(facts)
    store.add_sources(sources)
    answer = ("The next sync is computed from last_ts plus the sync interval. "
              "The sync module was written by Dana Whitfield.")
    turn = store.start_turn("p1", answer)
    found = verify_turn(store, turn, Config(), project=project).claims
    assert [c.decided_by for c in found] == ["reread", "deterministic"]
    assert found[0].verdict in ("supported", "partial")  # word overlap with the code itself
    assert found[0].span_ids == ["ledger/sync.py L4-L6"]
    assert found[1].verdict == "unsupported"  # nothing Claude read says who wrote it

    (project / "ledger" / "sync.py").write_text(content.replace("next sync", "next run"),
                                               encoding="utf-8")
    turn = store.start_turn("p2", "The next sync is computed from last_ts plus the sync interval.")
    [changed] = verify_turn(store, turn, Config(), project=project).claims
    assert (changed.verdict, changed.span_ids) == ("source-changed", ["ledger/sync.py"])


def test_command_output_cant_be_re_read_so_such_claims_are_not_checked(tmp_path):
    from qlaudified.store import Source, Store
    from qlaudified.verify import verify_turn

    store = Store(tmp_path / "s")
    store.add_sources([Source("$ pytest -q", "p1", "abc", "command-output", "no")])
    turn = store.start_turn("p1", "The test suite covers the sync scheduler at Fernwick.")
    [claim] = verify_turn(store, turn, Config(), project=tmp_path).claims
    assert claim.verdict == "not-checked"


def test_claudes_own_claims_are_never_evidence(notes):
    claude = Span("F99", "claude", "claude", "step 3", "Q3 revenue was $9.9M.", "9900000 USD",
                  hash="c")
    assert verdicts("Q3 revenue was $9.9M.", [*notes, claude])[0][1] in (
        "unsupported", "contradicted")

def test_a_cited_fact_id_goes_first(notes):
    index = Index(notes)
    revenue = at(notes, "L3")
    assert index.top(f"Headcount reached 48 [{revenue}]")[0][0].span_id == revenue
