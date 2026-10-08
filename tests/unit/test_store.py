"""Session store: IDs, dedupe, concurrency, CSV export, .gitignore (CAP-1, NFR-8)."""

import csv
import threading

from qlaudified.store import TEXT_CAP, Span, Store


def make(text: str, source: str = "notes/q3.md", locator: str = "L3") -> Span:
    return Span(span_id="", origin="local-doc", source=source, locator=locator, text=text,
                hash=str(abs(hash(text))))


def test_ids_count_up_and_repeats_keep_their_id(tmp_path):
    store = Store(tmp_path / ".claude" / ".qlaudified" / "sessions" / "s1")
    assert store.add_spans([make("a"), make("b", locator="L4")]) == ["S1", "S2"]
    assert store.add_span(make("a")) == "S1"
    assert [s.span_id for s in store.spans()] == ["S1", "S2"]


def test_gitignore_is_created_in_the_store_root(tmp_path):
    Store(tmp_path / ".claude" / ".qlaudified" / "sessions" / "s1")
    assert (tmp_path / ".claude" / ".qlaudified" / ".gitignore").read_text().strip().endswith("*")


def test_long_text_is_capped_with_the_full_copy_in_raw(tmp_path):
    store = Store(tmp_path / "s")
    span = make("x" * (TEXT_CAP + 10))
    store.add_span(span)
    assert len(store.spans()[0].text) == TEXT_CAP
    assert len((tmp_path / "s" / "raw" / f"{span.hash}.txt").read_text()) == TEXT_CAP + 10


def test_parallel_writers_do_not_fail_or_collide(tmp_path):
    folder = tmp_path / "s"
    errors = []

    def writer(n: int) -> None:
        try:
            Store(folder).add_spans([make(f"w{n}-{i}", locator=f"L{i}") for i in range(20)])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    spans = Store(folder).spans()
    assert errors == []
    assert len(spans) == 120 and len({s.span_id for s in spans}) == 120


def test_csv_matches_the_span_table(tmp_path):
    store = Store(tmp_path / "s")
    store.add_spans([make("Q3 revenue is estimated at $4.2M,\nper finance."), make("b", locator="L9")])
    with open(store.export_csv(), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["span_id"] for r in rows] == ["S1", "S2"]
    assert rows[0]["text"] == "Q3 revenue is estimated at $4.2M,\nper finance."
    assert rows[0]["agent_id"] == "main"


def test_new_spans_are_returned_once_per_agent(tmp_path):
    store = Store(tmp_path / "s")
    assert [s.span_id for s in store.add_new_spans([make("a"), make("b", locator="L4")])] == ["S1", "S2"]
    assert store.add_new_spans([make("a")]) == []
    sub = make("a")
    sub.agent_id = "agent-1"
    [new] = store.add_new_spans([sub])
    assert new.span_id not in ("S1", "S2")  # its own span (IDs may skip after ignored repeats)


def test_turns_keep_their_number_and_claims_round_trip(tmp_path):
    from qlaudified.store import Claim

    store = Store(tmp_path / "s")
    store.add_span(make("Q3 revenue is estimated at $4.2M."))
    assert store.start_turn("p1", "first").n == 1
    assert store.start_turn("p2", "second").n == 2
    assert store.start_turn("p1", "first, again").n == 1  # a second Stop in the same turn
    assert store.last_turn().prompt_id == "p2"
    claim = Claim("C2.1", "p2", "Q3 revenue was $4.2M.", ["S1"], "qualifier-dropped",
                  ["estimated"], "deterministic", 0.8, True)
    store.add_claims("p2", [claim])
    store.add_claims("p2", [claim])  # re-verifying replaces, never duplicates
    assert store.claims("p2") == [claim]
    with open(store.export_csv(), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["kind"] for r in rows] == ["span", "claim"]
    assert rows[1]["verdict"] == "qualifier-dropped" and rows[1]["span_ids"] == "S1"
