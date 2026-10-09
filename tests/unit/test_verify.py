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
    assert index.top("Pricing per seat [S5]")[0][0].span_id == "S5"


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


def test_code_values_are_checked_in_high_only():
    from qlaudified.config import Mode

    spans = spans_from("repo", "ledger/config.py", "ledger/sync.py")
    answer = ("SYNC_INTERVAL_S is 900 seconds. The next sync is scheduled from last_ts plus "
              "SYNC_INTERVAL_S.")
    medium, skipped = verify_answer(answer, spans, Turn(1, "p", answer, ""), Config())
    assert [c.text for c in medium] == [
        "The next sync is scheduled from last_ts plus SYNC_INTERVAL_S."] and skipped == 1
    high, _ = verify_answer(answer, spans, Turn(1, "p", answer, ""), Config(mode=Mode.HIGH))
    assert len(high) == 2
