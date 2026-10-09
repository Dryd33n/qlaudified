"""What qlaudified shows: injected deltas (INJ-1, INJ-2), reports (REP-2, REP-4), markers (REP-1)."""

import json

from qlaudified import inject, markers, report
from qlaudified.store import Claim, Span


def span(n: int, text: str, numbers: str = "", qualifiers: str = "", source: str = "q3.md",
         origin: str = "local-doc") -> Span:
    return Span(f"S{n}", origin, source, f"L{n}", text, numbers, qualifiers, hash=str(n))


REVENUE = span(3, "Q3 revenue is estimated at $4.2M, based on preliminary figures from finance.",
               "4200000 USD", "estimated; preliminary")
HEADCOUNT = span(4, "Headcount grew to 48 by September 30, 2026.", "48; 2026-09-30")


def test_line_format_is_a_plain_fact():
    assert inject.format_line(REVENUE) == (
        "[S3 q3.md L3] Q3 revenue is estimated at $4.2M, based on preliminary figures from "
        "finance.; source says: estimated, preliminary")


def test_delta_skips_spans_without_facts_and_search_titles():
    heading = span(1, "# Fernwick Co. Q3 update")
    title = span(5, "Release notes for 3.12", "3.12", origin="search-snippet")
    assert inject.build_delta([heading, title]) == ""
    assert inject.build_delta([heading, HEADCOUNT, REVENUE]).splitlines()[0].startswith("[S3 ")


def test_delta_never_exceeds_the_budget_and_counts_the_overflow():
    many = [span(n, f"Line {n} is estimated at ${n}M.", f"{n}000000 USD", "estimated",
                 source=f"doc{n % 4}.md") for n in range(1, 30)]
    for budget in (120, 300, 600):
        delta = inject.build_delta(many, budget)
        assert 0 < len(delta) <= budget
        assert delta.splitlines()[-1].startswith("+") and "more provenance spans from doc" in delta


def test_summary_line_puts_problems_first():
    claims = [
        Claim("C1.1", "p", "a", ["S3"], "supported", [], "deterministic", 0.9, True),
        Claim("C1.2", "p", "b", ["S3"], "qualifier-dropped", ["estimated", "preliminary"],
              "deterministic", 0.8, True),
    ]
    assert report.summary_line(claims, skipped=2) == (
        "qlaudified: 2 claims checked (2 non-critical skipped) · 1 qualifier dropped (estimated)"
        " · 1 supported · /qlaudified report")
    assert report.summary_line(claims[:1]) == "qlaudified: 1 claim checked · 1 supported"


def test_turn_report_is_saved_as_markdown_and_json(tmp_path):
    claim = Claim("C2.1", "p", "Q3 revenue was $4.2M.", ["S3"], "qualifier-dropped",
                  ["estimated", "preliminary"], "deterministic", 0.8, True)
    md = report.write_turn_report(tmp_path, 2, "p", [claim], {"S3": REVENUE}, mode="medium")
    text = md.read_text(encoding="utf-8")
    assert md.name == "turn-2.md"
    assert "1. **qualifier dropped** (rules): Q3 revenue was $4.2M." in text
    assert "   - dropped: estimated, preliminary" in text
    assert '   - [S3] q3.md L3: "Q3 revenue is estimated' in text
    data = json.loads((tmp_path / "reports" / "turn-2.json").read_text(encoding="utf-8"))
    assert data["claims"][0]["verdict"] == "qualifier-dropped" and data["spans"]["S3"]["locator"] == "L3"


def test_markers_cite_spans_and_name_dropped_qualifiers():
    text = "Q3 revenue was $4.2M. Headcount grew to 48 by September 30, 2026.\n"
    marked, still_open = markers.add_markers(text, [REVENUE, HEADCOUNT])
    assert marked == ("Q3 revenue was $4.2M [S3, qualifier: estimated, preliminary]. "
                      "Headcount grew to 48 by September 30, 2026 [S4].\n")
    assert not still_open


def test_markers_leave_code_tables_and_unmatched_sentences_alone():
    text = "```\nrevenue = 4.2  # $4.2M\n```\n| Q3 | $4.2M |\nNothing to cite here, 7 times over."
    marked, still_open = markers.add_markers(text, [REVENUE])
    assert marked == text and not still_open
    # A fence opened in an earlier batch is still open.
    assert markers.add_markers("Q3 revenue was $4.2M.", [REVENUE], in_fence=True) == (
        "Q3 revenue was $4.2M.", True)
