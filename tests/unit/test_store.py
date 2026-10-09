"""The ledger: fact IDs, dedupe, concurrency, steps, sources, use tracking, and the rolling
read-only provenance.csv (PROV-1, PROV-4, PROV-7, NFR-8)."""

import csv
import os
import stat
import threading

import pytest

from qlaudified.store import TEXT_CAP, Claim, Source, Span, Store


def make(text: str, source: str = "notes/q3.md", locator: str = "L3", **extra) -> Span:
    return Span(span_id="", origin="local-doc", source=source, locator=locator, text=text,
                hash=str(abs(hash(text))), **extra)


def rows(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_ids_count_up_and_repeats_keep_their_id(tmp_path):
    store = Store(tmp_path / ".claude" / ".qlaudified" / "sessions" / "s1")
    assert store.add_spans([make("a"), make("b", locator="L4")]) == ["F1", "F2"]
    assert store.add_span(make("a")) == "F1"
    assert [s.span_id for s in store.spans()] == ["F1", "F2"]


def test_gitignore_is_created_in_the_store_root(tmp_path):
    Store(tmp_path / ".claude" / ".qlaudified" / "sessions" / "s1")
    assert (tmp_path / ".claude" / ".qlaudified" / ".gitignore").read_text().strip().endswith("*")


def test_a_fact_is_one_sentence_so_long_text_is_cut(tmp_path):
    store = Store(tmp_path / "s")
    store.add_span(make("x" * (TEXT_CAP + 10)))
    assert len(store.spans()[0].text) == TEXT_CAP
    assert not (tmp_path / "s" / "raw").exists()  # no passages, no raw copies


def test_parallel_writers_do_not_fail_or_collide(tmp_path):
    folder = tmp_path / "s"
    errors = []

    def writer(n: int) -> None:
        try:
            store = Store(folder)
            store.add_spans([make(f"w{n}-{i}", locator=f"L{i}") for i in range(20)])
            store.export_csv()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(rows(folder / "provenance.csv")) == 120


def test_provenance_csv_has_the_req_3_2_columns_and_is_read_only(tmp_path):
    store = Store(tmp_path / "s")
    store.add_spans([make("Q3 revenue is estimated at $4.2M,\nper finance.", numbers="4200000 USD",
                          qualifiers="estimated", category="Internal Document", step=2)])
    path = store.export_csv()
    [row] = rows(path)
    assert list(row)[:7] == ["fact_id", "claim", "value", "origin", "source", "locator",
                             "source_qualifiers"]
    assert row["claim"] == "Q3 revenue is estimated at $4.2M, per finance."  # one line per row
    assert (row["fact_id"], row["origin"], row["step"]) == ("F1", "Internal Document", "2")
    assert not os.access(path, os.W_OK)
    with pytest.raises(PermissionError):
        path.write_text("edited by the agent")


def test_any_edit_is_undone_at_the_next_rewrite(tmp_path):
    store = Store(tmp_path / "s")
    store.add_span(make("Headcount grew to 48."))
    path = store.export_csv()
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    path.write_text("tampered", encoding="utf-8")
    store.export_csv()
    assert rows(path)[0]["claim"] == "Headcount grew to 48."
    assert not os.access(path, os.W_OK)


def test_new_facts_are_returned_once_per_agent(tmp_path):
    store = Store(tmp_path / "s")
    assert [s.span_id for s in store.add_new_spans([make("a"), make("b", locator="L4")])] == [
        "F1", "F2"]
    assert store.add_new_spans([make("a")]) == []
    sub = make("a")
    sub.agent_id = "agent-1"
    [new] = store.add_new_spans([sub])
    assert new.span_id not in ("F1", "F2")


def test_steps_sources_and_provided_files(tmp_path):
    store = Store(tmp_path / "s")
    assert store.next_step("toolu_1", "Read") == 1
    assert store.next_step("toolu_2", "Bash") == 2
    assert store.next_step("toolu_1", "Read") == 1  # the same call keeps its number
    assert store.current_step() == 2
    store.add_sources([Source("q3.md", "L1-L5", "abc", "local-doc", "file", step=1),
                       Source("q3.md", "L1-L5", "abc", "local-doc", "file", step=3)])
    assert [(s.source, s.step) for s in store.sources()] == [("q3.md", 1)]
    store.add_provided(["q3.md"], "p1")
    assert store.provided() == {"q3.md"}


def test_first_use_keeps_its_qualifiers_and_later_uses_accumulate(tmp_path):
    store = Store(tmp_path / "s")
    fid = store.add_span(make("Q3 revenue is estimated at $4.2M.", qualifiers="estimated"))
    assert store.record_use(fid, 4, "reasoning", "") is True
    assert store.record_use(fid, 7, "Write notes.md", "estimated") is False
    assert store.record_use(fid, 7, "Write notes.md", "estimated") is False  # no duplicates
    store.append_impact(fid, "step 4: basis of the summary")
    store.update_fact(fid, category="Internal Document")
    fact = store.spans()[0]
    assert (fact.first_use_step, fact.first_use_qualifiers) == (4, "")  # dropped at first use
    assert fact.uses == "4:reasoning; 7:Write notes.md"
    assert fact.impact == "step 4: basis of the summary" and fact.category == "Internal Document"
    store.delete_fact(fid)
    assert store.spans() == []


def test_turns_keep_their_number_and_claims_go_to_claims_csv(tmp_path):
    store = Store(tmp_path / "s")
    store.add_span(make("Q3 revenue is estimated at $4.2M."))
    assert store.start_turn("p1", "first").n == 1
    assert store.start_turn("p2", "second").n == 2
    assert store.start_turn("p1", "first, again").n == 1  # a second Stop in the same turn
    assert store.last_turn().prompt_id == "p2"
    claim = Claim("C2.1", "p2", "Q3 revenue was $4.2M.", ["F1"], "qualifier-dropped",
                  ["estimated"], "deterministic", 0.8, True)
    store.add_claims("p2", [claim])
    store.add_claims("p2", [claim])  # re-verifying replaces, never duplicates
    assert store.claims("p2") == [claim]
    store.export_csv()
    [row] = rows(store.claims_path)
    assert (row["verdict"], row["fact_ids"]) == ("qualifier-dropped", "F1")
    assert len(rows(store.csv_path)) == 1  # facts only in provenance.csv
