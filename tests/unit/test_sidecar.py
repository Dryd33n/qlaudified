"""High sidecar with a fake backend: flagged sentences only, verbatim qualifiers, and its finds
reaching both the next delta and Stop (SID-1, SID-2)."""

from qlaudified import sidecar
from qlaudified.backends.fake import FakeBackend
from qlaudified.config import Config
from qlaudified.store import Span, Store, Turn
from qlaudified.verify import verify_answer

REPORT = Span("S1", "local-doc", "q3-report.md", "L3-L4",
              "Q3 revenue was $4.2M, unaudited as of mid-October.\n"
              "The team met on a Tuesday to go over it.\nok", "4200000 USD", hash="a")
TITLE = Span("S2", "search-snippet", "https://x.org", "title", "Fernwick raises $9M Series A",
             "9000000 USD", hash="b")


def test_only_flagged_sentences_are_sent():
    flagged = sidecar.flag_sentences([REPORT, TITLE])
    assert [(f, s.span_id, t) for f, s, t in flagged] == [
        ("F1", "S1", "Q3 revenue was $4.2M, unaudited as of mid-October."),
        ("F2", "S1", "The team met on a Tuesday to go over it.")]
    prompt = sidecar.build_prompt(flagged)
    assert "F1: Q3 revenue was $4.2M" in prompt and "Series A" not in prompt and "\nok" not in prompt


def test_qualifiers_must_appear_verbatim_and_be_new():
    flagged = sidecar.flag_sentences([REPORT])
    fake = FakeBackend([{"sentences": [
        {"id": "F1", "criticality": 0.9,
         "qualifiers": ["Unaudited", "as of mid-October", "approximately", "per the CFO"]},
        {"id": "F2", "criticality": 7, "qualifiers": []},
    ]}])
    rows = sidecar.classify(flagged, fake)
    assert rows[0]["qualifiers"] == ["unaudited", "as of mid-october"]
    assert rows[1]["criticality"] == 1.0 and rows[1]["qualifiers"] == []


def test_finds_are_injected_once_and_count_at_stop(tmp_path):
    store = Store(tmp_path / "s")
    store.add_spans([Span("", "local-doc", "q3-report.md", "L3", REPORT.text.splitlines()[0],
                          "4200000 USD", hash="a")])
    store.add_sidecar([{"span_id": "S1", "sentence": REPORT.text.splitlines()[0],
                        "criticality": 0.9, "qualifiers": ["unaudited"], "agent_id": "main"}])
    rows = store.take_sidecar("main")
    assert sidecar.format_lines(rows) == [
        '[S1] source also qualifies: unaudited ("Q3 revenue was $4.2M, unaudited as of mid-October.")']

    assert store.take_sidecar("main") == []  # once per agent
    spans = store.spans()
    answer = "Q3 revenue was $4.2M."
    plain, _ = verify_answer(answer, spans, Turn(1, "p", answer, ""), Config())
    with_sidecar, _ = verify_answer(answer, spans, Turn(1, "p", answer, ""), Config(),
                                    extra_qualifiers=store.sidecar_qualifiers())
    assert plain[0].verdict == "supported"  # the lexicon alone misses "unaudited"
    assert (with_sidecar[0].verdict, with_sidecar[0].dropped_qualifiers) == (
        "qualifier-dropped", ["unaudited"])


def test_run_stores_rows_and_logs_usage(tmp_path, monkeypatch):
    from qlaudified import backends

    store = Store(tmp_path / "s")
    [span_id] = store.add_spans([REPORT])
    fake = FakeBackend([{"sentences": [{"id": "F1", "criticality": 0.8,
                                        "qualifiers": ["unaudited"]}]}])
    fake.last_usage = {"cost_usd": 0.0005, "wall_ms": 3000}
    monkeypatch.setattr(backends, "get_backend", lambda name, model=None: fake)
    assert sidecar.run({"session_dir": str(store.session_dir), "project": str(tmp_path),
                        "span_ids": [span_id]}) == 1
    assert store.sidecar_qualifiers() == ["unaudited"]
    assert '"tier": "sidecar"' in (store.session_dir / "usage.jsonl").read_text(encoding="utf-8")
