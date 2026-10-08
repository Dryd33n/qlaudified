"""Span indexer and hedge lexicon (CAP-2), on the Fernwick sandbox sentences."""

import pytest

from qlaudified import lexicon
from qlaudified.indexer import extract_dates, extract_numbers, find_hedges, normalize_number


@pytest.mark.parametrize("text, value", [
    ("$4.2M", 4_200_000.0),
    ("4.2 million USD", 4_200_000.0),
    ("15 minutes", 900.0),
    ("900 seconds", 900.0),
    ("1,250", 1250.0),
    ("no numbers here", None),
])
def test_normalize_number(text, value):
    assert normalize_number(text) == value


@pytest.mark.parametrize("text, numbers, dates", [
    ("Q3 revenue is estimated at $4.2M, based on preliminary figures from finance.",
     ["4200000 USD"], []),
    ("Headcount grew to 48 by September 30, 2026.", ["48"], ["2026-09-30"]),
    ("The Lisbon office may open in early 2027, pending the lease review.", [], ["2027"]),
    ("The Fernwick Ledger launch is tentatively scheduled for November 18, 2026.",
     [], ["2026-11-18"]),
    ("Pricing is expected to start at $12 per seat per month.", ["12 USD"], []),
    ("Roughly 15 minutes; SYNC_INTERVAL_S = 900", ["900 s", "900"], []),
    ("Growth was 12% in Sept 2026 and 3.5 hours on 2026-10-08.",
     ["12 %", "12600 s"], ["2026-09", "2026-10-08"]),
])
def test_numbers_and_dates(text, numbers, dates):
    assert extract_numbers(text) == numbers
    assert extract_dates(text) == dates


@pytest.mark.parametrize("text", ["Q3", "L22-L24", "span S14", "v2 of the API", "5 m of cable"])
def test_labels_and_lowercase_magnitudes_are_not_amounts(text):
    assert all("000000" not in n for n in extract_numbers(text))
    assert "3" not in extract_numbers("Q3") and "22" not in extract_numbers("L22")


def test_urls_carry_no_numbers():
    assert extract_numbers("see https://example.com/page/108931#s2 and [x](https://a.b/9)") == []


@pytest.mark.parametrize("text, expected", [
    ("Q3 revenue is estimated at $4.2M, based on preliminary figures.",
     {"estimate": ["estimated", "preliminary"]}),
    ("The launch is tentatively scheduled.", {"tentative": ["tentatively"]}),
    ("Pricing is expected to start at $12, subject to change.",
     {"likelihood": ["expected to"], "tentative": ["subject to change"]}),
    ("The office may open, pending the lease review.",
     {"modal": ["may"], "tentative": ["pending"]}),
    ("Roughly 15 minutes", {"estimate": ["roughly"]}),
    ("A memo about pricing, around the office.", {}),
    ("about 15 minutes", {"estimate": ["about"]}),
    ("Reportedly, according to finance.", {"attribution": ["reportedly", "according to"]}),
])
def test_find_hedges(text, expected):
    assert find_hedges(text) == expected


def test_may_the_month_is_not_a_hedge_and_may_the_hedge_is_not_a_month():
    assert extract_dates("It may open in 2027.") == ["2027"]
    assert extract_dates("Opens May 4, 2027.") == ["2027-05-04"]


def test_strength_order_and_merge():
    assert sorted(lexicon.STRENGTH_ORDER) == sorted(lexicon.HEDGES)
    assert lexicon.strongest({"modal", "estimate"}) == "estimate"
    assert lexicon.strongest({"modal", "attribution"}) == "attribution"
    assert lexicon.strongest(set()) is None
    merged = lexicon.merged({"estimate": ["Ballpark"], "custom": ["iffy"]})
    assert "ballpark" in merged["estimate"] and merged["custom"] == ["iffy"]
    assert "ballpark" not in lexicon.HEDGES["estimate"]
    assert find_hedges("a ballpark figure", merged) == {"estimate": ["ballpark"]}
