"""The Provenance Administrator with a fake backend: threshold, judgment fields, verbatim checks,
the final report, and the transcript reasoning it reads (PROV-2 to PROV-6, INT-2, REP-2)."""

import json

from qlaudified import administrator, tracking, transcript
from qlaudified.backends.fake import FakeBackend
from qlaudified.backends.none import NoneBackend
from qlaudified.store import Claim, Span, Store


def fact(text: str, numbers: str = "", qualifiers: str = "", step: int = 1, source: str = "q3.md",
         locator: str = "L3") -> Span:
    return Span("", "local-doc", source, locator, text, numbers, qualifiers, hash=text[:16],
                category="Internal Document", step=step)


def step_two(store: Store):
    """Step 2: Claude reads a figure from step 1 into a note and derives one of its own."""
    parts = [("reasoning", "Revenue was $4.2M, so per head that's $87.5K.", True)]
    scan = tracking.scan(store.spans(), 2, parts)
    for use in scan.uses:
        store.record_use(use.fact.span_id, 2, use.where, use.qualifiers)
    claims = store.add_new_spans(tracking.claim_rows(scan.claims, 2, "main", "p1"))
    return scan, claims


def test_no_call_when_nothing_critical_happened(tmp_path):
    store = Store(tmp_path / "s")
    fake = FakeBackend([{"facts": [], "claims": [], "uses": []}])
    empty = tracking.Scan([], [], "")
    assert administrator.run_step(store, fake, 1, "Glob", "*.md", [], empty, []) == {}
    assert fake.prompts == []
    assert administrator.run_step(store, NoneBackend(), 1, "Read", "q3.md",
                                  [fact("x 1")], empty, []) == {}


def test_judgment_fields_are_merged_and_checked(tmp_path):
    store = Store(tmp_path / "s")
    new = store.add_new_spans([
        fact("Q3 revenue was $4.2M, unaudited.", "4200000 USD"),
        fact("Page 3 of 7.", "3; 7", locator="L9"),
        fact("Headcount grew to 48.", "48", locator="L4"),
    ])
    scan, claims = step_two(store)
    assert [c.text for c in claims] == ["Revenue was $4.2M, so per head that's $87.5K."]
    assert claims[0].numbers == "87500 USD"  # only the figure no source states
    fake = FakeBackend([{
        "facts": [
            {"id": "F1", "critical": True, "extra_qualifiers": ["Unaudited", "per the CFO"]},
            {"id": "F2", "critical": False, "extra_qualifiers": []},
            {"id": "F99", "critical": False, "extra_qualifiers": []},
        ],
        "claims": [{"id": claims[0].span_id, "origin": "Hybrid", "primary_source": "F1",
                    "sources_agree": "yes"}],
        "uses": [{"id": "U1", "impact": "Basis for the per-head figure."}],
    }])
    fake.last_usage = {"cost_usd": 0.0009}
    usage = administrator.run_step(store, fake, 3, "Write", "notes.md", new, scan, claims)
    assert usage == {"cost_usd": 0.0009}
    rows = {s.span_id: s for s in store.spans()}
    assert rows["F1"].qualifiers == "unaudited"  # verbatim only: "per the CFO" isn't in the text
    assert "F2" not in rows  # trivia dropped from the ledger
    own = rows[claims[0].span_id]
    assert (own.category, own.primary_source, own.sources_agree) == ("Hybrid", "F1", "yes")
    assert rows["F1"].impact == "step 3: Basis for the per-head figure."
    prompt = fake.prompts[0]
    assert prompt.startswith(administrator.STEP_INSTRUCTIONS.split("{")[0])  # stable prefix
    assert "F1: Q3 revenue was $4.2M, unaudited." in prompt and "Ledger facts" in prompt


def test_invalid_answers_change_nothing(tmp_path):
    store = Store(tmp_path / "s")
    new = store.add_new_spans([fact("Headcount grew to 48.", "48")])
    scan = tracking.Scan([], [], "")
    for answer in (None, "nope", {"facts": "x"}, {"claims": [{"id": "F1", "origin": "Guess"}]}):
        administrator.run_step(store, FakeBackend([answer]), 2, "Read", "", new, scan, [])
    [row] = store.spans()
    assert (row.qualifiers, row.category, row.impact) == ("", "Internal Document", "")


def test_final_report_adds_conclusion_impact_and_a_summary(tmp_path):
    store = Store(tmp_path / "s")
    store.add_span(fact("Q3 revenue is estimated at $4.2M.", "4200000 USD", "estimated"))
    claim = Claim("C1.1", "p1", "Q3 revenue was $4.2M.", ["F1"], "qualifier-dropped",
                  ["estimated"], "deterministic", 0.8, True)
    fake = FakeBackend([{"facts": [{"id": "F1", "final_impact": "The headline figure."},
                                   {"id": "F7", "final_impact": "not offered"}],
                         "summary": "Rests on one estimate; the qualifier was lost."}])
    summary, _ = administrator.run_final(store, fake, [claim], "Q3 revenue was $4.2M.")
    assert summary == "Rests on one estimate; the qualifier was lost."
    assert store.spans()[0].impact == "conclusion: The headline figure."
    assert "[qualifier-dropped] Q3 revenue was $4.2M." in fake.prompts[0]


def test_reasoning_is_the_text_since_the_last_user_line(tmp_path):
    path = tmp_path / "t.jsonl"
    entries = [
        {"type": "user", "message": {"content": "old prompt"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Old thoughts."}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a"}]}},
        {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": ""}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Now the note."}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "b"}]}},
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\nnot json\n", encoding="utf-8")
    assert transcript.reasoning_before(str(path), "b") == "Now the note."
    assert transcript.reasoning_before(str(path), "missing") == ""
    assert transcript.reasoning_before(None, "b") == ""


def test_uses_are_found_per_clause_and_paths_are_not_figures():
    facts = [fact("Q3 revenue is estimated at $4.2M.", "4200000 USD", "estimated")]
    for f in facts:
        f.span_id = "F1"
    scan = tracking.scan(facts, 2, [
        ("reasoning", "Revenue was about $4.2M, but churn rose to 3%.", True),
        ("Agent prompt", "Read C:\\Temp\\tmp6cqrmw\\q3.md and toolu_01abc then report.", True),
    ])
    assert [(u.fact.span_id, u.qualifiers) for u in scan.uses] == [("F1", "about")]
    assert [(s, n) for s, _, n in scan.claims] == [
        ("Revenue was about $4.2M, but churn rose to 3%.", ["3 %"])]
