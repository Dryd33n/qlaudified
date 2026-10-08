"""Seed corpus (eval/tasks/*.toml): the ground truth matches the sandboxes, and every expected
verdict holds when the task's files are the session's spans (VER-1..3)."""

import tomllib
from pathlib import Path

import pytest

from qlaudified import indexer
from qlaudified.config import Config
from qlaudified.store import Turn
from qlaudified.testing.spans import spans_from_files
from qlaudified.verify import verify_answer
from qlaudified.verify.candidates import Index

REPO = Path(__file__).resolve().parents[2]
TASKS = sorted((REPO / "eval" / "tasks").glob("*.toml"))
TYPES = {"single-hop", "multi-hop", "conflict", "compaction", "no-source"}


def load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def task_spans(task: dict):
    folder = REPO / task["sandbox"]
    files = sorted(str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*.md"))
    return spans_from_files(folder, *files)


def test_one_task_per_type():
    assert sorted(load(p)["type"] for p in TASKS) == sorted(TYPES)


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.stem)
def test_ground_truth_matches_the_sandbox(path):
    task = load(path)
    folder = REPO / task["sandbox"]
    assert task["id"] == path.stem == folder.name
    assert (folder / "prompt.txt").exists()
    assert all(p.stat().st_size < 1024 for p in folder.rglob("*") if p.is_file())
    for fact in task.get("facts", []):
        lines = (folder / fact["source"]).read_text(encoding="utf-8").splitlines()
        line = lines[int(fact["locator"].lstrip("L")) - 1]
        assert fact["value"] in indexer.extract_numbers(line) + indexer.extract_dates(line), line
        found = [w for words in indexer.find_hedges(line).values() for w in words]
        assert sorted(found) == sorted(fact["qualifiers"]), line


def verdict(claim: str, spans) -> tuple[str, list[str]]:
    [c], _ = verify_answer(claim, spans, Turn(1, "p", claim, ""), Config())
    return c.verdict, c.span_ids


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.stem)
def test_expected_verdicts(path):
    task = load(path)
    spans = task_spans(task)
    index = Index(spans)
    for fact in task.get("facts", []):
        want = next(s.span_id for s in spans
                    if s.source == fact["source"] and s.locator == fact["locator"])
        for key in ("kept", "dropped"):
            if key in fact:
                assert want in [s.span_id for s, _ in index.top(fact[key], k=3)], fact[key]
        assert verdict(fact["kept"], spans) == ("supported", [want]), fact["kept"]
        if "dropped" in fact:
            assert verdict(fact["dropped"], spans) == ("qualifier-dropped", [want]), fact["dropped"]
    for item in task.get("unsupported", []):
        assert verdict(item["claim"], spans)[0] == "unsupported", item["claim"]
