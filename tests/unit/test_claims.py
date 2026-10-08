"""Claim extraction and critical-claim tagging (VER-1)."""

import pytest

from qlaudified.verify.claims import criticality, extract_claims, is_critical

REPO_ANSWER = (
    "Ledger syncs every 900 seconds, which is 15 minutes. The code defines `SYNC_INTERVAL_S = 900` "
    "in `ledger/config.py:6`, and `ledger/sync.py` uses it as `last_ts + SYNC_INTERVAL_S` to "
    "schedule the next sync."
)


def test_compound_sentences_split_at_clause_joints():
    assert extract_claims(REPO_ANSWER) == [
        "Ledger syncs every 900 seconds",
        "which is 15 minutes.",
        "The code defines `SYNC_INTERVAL_S = 900` in `ledger/config.py:6`",
        "`ledger/sync.py` uses it as `last_ts + SYNC_INTERVAL_S` to schedule the next sync.",
    ]


def test_and_splits_only_between_two_stated_numbers():
    assert extract_claims("Revenue was $4.2M and headcount grew to 48.") == [
        "Revenue was $4.2M", "headcount grew to 48."]
    assert extract_claims("Tom and Jerry wrote the Q3 update memo.") == [
        "Tom and Jerry wrote the Q3 update memo."]


def test_lists_tables_and_quotes_count_code_and_headings_do_not():
    lines = [
        "# Summary",
        "",
        "- Q3 revenue is estimated at $4.2M.",
        "- Headcount grew to 48.",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        "| Q3 revenue | $4.2M |",
        "",
        "```python",
        "SYNC_INTERVAL_S = 900  # this is code, not a claim",
        "```",
        "> The Lisbon office may open in early 2027.",
        "",
        "Sources:",
        "- [Q3 update](notes/q3-update.md)",
    ]
    assert extract_claims("\n".join(lines)) == [
        "Q3 revenue is estimated at $4.2M.",
        "Headcount grew to 48.",
        "Q3 revenue, $4.2M",
        "The Lisbon office may open in early 2027.",
    ]


def test_abbreviations_and_decimals_do_not_end_a_sentence():
    assert extract_claims("Fernwick Co. reported $4.2M in Q3. The launch is set for Nov. 18, 2026.") == [
        "Fernwick Co. reported $4.2M in Q3.", "The launch is set for Nov. 18, 2026."]


@pytest.mark.parametrize("claim, score", [
    ("Q3 revenue was $4.2M.", 1.0),
    ("The launch is on November 18, 2026.", 1.0),
    ("Retries may run sooner than that.", 0.8),
    ("The new parser is faster than the old one.", 0.7),
    ("The config lives in the Ledger repository.", 0.5),
    ("This matters most when answers are used for decisions.", 0.3),
    ("I read both files and found the figure.", 0.0),
    ("If you give me the URLs or IDs, the comment history can be checked.", 0.0),
])
def test_criticality(claim, score):
    assert criticality(claim) == score


def test_medium_skips_non_critical_claims():
    assert is_critical("Q3 revenue was $4.2M.")
    assert not is_critical("This matters most when answers are used for decisions.")
    assert is_critical("This matters most when answers are used for decisions.", threshold=0.25)
