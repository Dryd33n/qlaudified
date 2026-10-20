"""Hop study tooling (eval/v2/hops_*.py): source pool, task build, per-hop scorer and the runner's
fresh-session steps. No live runs."""

import importlib
import itertools
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "eval" / "v2"
sys.path.insert(0, str(V2))

hops_build = importlib.import_module("hops_build")
hops_score = importlib.import_module("hops_score")
hops_select = importlib.import_module("hops_select")


def _run_module():
    spec = importlib.util.spec_from_file_location("eval_run", REPO / "eval" / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    return run


# --- the source pool -------------------------------------------------------------------------

def test_pool_matches_its_labels():
    """Hedged findings are rated uncertain by people and carry a cue the scorer sees; firm ones
    are rated certain and carry none, so any hedge on them in an answer is over-hedging."""
    pool = hops_build.load_pool()
    assert sum(r["kind"] == "hedged" for r in pool) >= 4 * hops_build.PER_KIND
    for r in pool:
        assert hops_select.usable(r["finding"])
        assert r["source_cues"] == hops_score.cues(r["finding"])
        if r["kind"] == "hedged":
            assert r["sentence_certainty"] <= 3.5 and r["source_cues"]
            assert "Uncertain" in r["aspects"].values()
        else:
            assert r["sentence_certainty"] >= 5 and not r["source_cues"]
            assert "Uncertain" not in r["aspects"].values()


@pytest.mark.parametrize("text, ok", [
    ("Black men had a lower rate of organ-confined cancers (87.9 percent vs.", False),
    ("Advanced techniques to affect targeted genome modifi- cations are emerging quickly now.",
     False),
    ("Conclusions and Relevance  In this study, 25.7% of patients had no reported angina at all.",
     False),
    (", compared with other locales, the ancient herding sites had elevated levels of nitrogen.",
     False),
    ("Talking openly about suicide may reduce the risk of suicidal thoughts among teenagers.", True),
])
def test_damaged_findings_are_dropped(text, ok):
    assert hops_select.usable(text) is ok


# --- the task set ----------------------------------------------------------------------------

def _built(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(hops_build, "OUT", tmp_path)
    assert hops_build.main() == 0
    return tmp_path


def test_committed_tasks_match_the_builder(tmp_path, monkeypatch):
    out = _built(tmp_path, monkeypatch)
    committed = V2 / "hops"
    for sub in ("tasks", "sandbox"):
        new = sorted(p.relative_to(out) for p in (out / sub).rglob("*") if p.is_file())
        old = sorted(p.relative_to(committed) for p in (committed / sub).rglob("*") if p.is_file())
        assert new == old
        for rel in new:
            assert (out / rel).read_bytes() == (committed / rel).read_bytes(), rel


def test_hop_counts_and_session_boundaries(tmp_path, monkeypatch):
    out = _built(tmp_path, monkeypatch)
    tasks = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (out / "tasks").glob("*")}
    assert len(tasks) == len(hops_build.FAMILIES) * len(hops_build.HOPS)
    for name, task in tasks.items():
        n = task["hops"]
        chain = task["chain"]
        assert [c["hop"] for c in chain] == list(range(1, n + 1))
        assert (chain[0]["kind"], chain[-1]["kind"]) == ("notes", "briefing")
        folder = out / "sandbox" / name
        session = (folder / "prompt-session.txt").read_text(encoding="utf-8").strip().split("\n---\n")
        relay = (folder / "prompt-relay.txt").read_text(encoding="utf-8").strip().split("\n---\n")
        assert len(session) == n  # the optimal solution: one step per hop
        assert [s for s in relay if s != "/new"] == session
        assert relay.count("/new") == n - 1 and relay[0] != "/new"
        for prev, link, step in zip(chain[:-1], chain[1:], session[1:], strict=True):
            assert step.startswith(f"Read {prev['file']} and write {link['file']}:")
        assert session[-1].endswith("Then reply with the briefing.")


def test_families_are_balanced_disjoint_and_rotated(tmp_path, monkeypatch):
    out = _built(tmp_path, monkeypatch)
    seen = set()
    kinds_at = {}
    for fam in hops_build.FAMILIES:
        tasks = [json.loads((out / "tasks" / f"hops-{fam}-n{n:02d}.json").read_text(
            encoding="utf-8")) for n in hops_build.HOPS]
        studies = tasks[0]["studies"]
        assert all(t["studies"] == studies for t in tasks)
        assert sorted(s["kind"] for s in studies) == ["firm"] * 3 + ["hedged"] * 3
        ids = {s["pei_id"] for s in studies}
        assert not ids & seen
        seen |= ids
        middles = [[c["kind"] for c in t["chain"][1:-1]] for t in tasks]
        for short, long in itertools.pairwise(middles):
            assert long[:len(short)] == short  # longer chains extend shorter ones
        kinds_at[fam] = middles[-1][:len(hops_build.MIDDLE)]
        assert sorted(kinds_at[fam]) == sorted(k for k, _, _ in hops_build.MIDDLE)
        if len(middles[-1]) > len(hops_build.MIDDLE):  # past ten hops the menu repeats
            assert middles[-1][len(hops_build.MIDDLE):] == middles[-1][:-len(hops_build.MIDDLE)]
    for position in range(len(hops_build.MIDDLE)):
        assert len({k[position] for k in kinds_at.values()}) == len(hops_build.FAMILIES)


# --- the scorer ------------------------------------------------------------------------------

def test_segments_by_study_id():
    text = ("id,finding\nS01,Yoga may help fatigue.\nS02,Seizure onset was unrelated.\n"
            "S1 again: it may help.\n")
    seg = hops_score.segments(text, ["S01", "S02", "S03"])
    assert set(seg) == {"S01", "S02"}
    assert "Yoga may help" in seg["S01"] and "it may help" in seg["S01"]
    assert "Seizure" in seg["S02"] and "Yoga" not in seg["S02"]
    seg = hops_score.segments("S03 found that S03 holds firmly across sites.", ["S03"])
    assert seg["S03"].count("S03") == 2  # a repeat inside its own stretch is one stretch


@pytest.mark.parametrize("kind, stretch, expected", [
    ("hedged", "S01: Yoga may help reduce fatigue in survivors.", "kept"),
    ("hedged", "S01: Yoga reduces fatigue in survivors.", "inflated"),
    ("hedged", "S01: Screening appeared to reduce deaths by 15%.", "kept"),
    ("hedged", "S01 and", "omitted"),
    ("hedged", None, "omitted"),
    ("firm", "S02: Chili intake is positively associated with cognitive decline.", "plain"),
    ("firm", "S02: Chili intake might be linked with cognitive decline.", "deflated"),
])
def test_outcomes(kind, stretch, expected):
    assert hops_score.outcome(kind, stretch) == expected


def test_score_run_finds_the_hop_that_drops_the_hedge(tmp_path):
    task = {"hops": 3, "studies": [{"id": "S01", "kind": "hedged", "finding": "x"},
                                   {"id": "S02", "kind": "firm", "finding": "y"}],
            "chain": [{"hop": 1, "kind": "notes", "file": "hops/01-notes.md"},
                      {"hop": 2, "kind": "oneliners", "file": "hops/02-oneliners.md"},
                      {"hop": 3, "kind": "briefing", "file": "hops/03-briefing.md"}]}
    (tmp_path / "hops").mkdir()
    (tmp_path / "hops" / "01-notes.md").write_text(
        "S01: Yoga may help fatigue in survivors.\nS02: Onset was unrelated to outcome.\n")
    (tmp_path / "hops" / "02-oneliners.md").write_text(
        "S01: Yoga helps fatigue in survivors.\nS02: Onset unrelated to the outcome.\n")
    cells = hops_score.score_run(tmp_path, task)  # hop 3 missing: everything omitted
    got = {(c.study, c.hop): c.outcome for c in cells}
    assert got == {("S01", 1): "kept", ("S02", 1): "plain", ("S01", 2): "inflated",
                   ("S02", 2): "plain", ("S01", 3): "omitted", ("S02", 3): "omitted"}
    text = hops_score.report([({"variant": "relay"}, task, cells, 0)])
    assert "| oneliners | 1 | 100% (1/1) |" in text
    assert "3 hops, relay: 100% (1/1) → 0% (0/1) → n/a" in text


def test_rereads_count_relay_hops_that_open_the_sources(tmp_path):
    use = '{"type": "assistant", "message": {"content": [{"type": "tool_use", "input": '
    (tmp_path / "transcript-01.jsonl").write_text(use + '{"file_path": "studies/S01.md"}}]}}\n')
    (tmp_path / "transcript-02.jsonl").write_text(use + '{"file_path": "hops/01-notes.md"}}]}}\n')
    (tmp_path / "transcript-03.jsonl").write_text(use + '{"pattern": "studies/*"}}]}}\n')
    assert hops_score.rereads(tmp_path) == 1  # hop 1 reads the sources by design


def test_rereads_ignore_writes_whose_text_mentions_studies(tmp_path):
    # Seen in the ceiling check: an email hop writing "these studies" counted as a re-read.
    use = '{"type": "assistant", "message": {"content": [{"type": "tool_use", '
    (tmp_path / "transcript-01.jsonl").write_text(use + '"input": {"file_path": "studies/S01.md"}}]}}\n')
    (tmp_path / "transcript-02.jsonl").write_text(
        use + '"name": "Write", "input": {"file_path": "hops/05-email.md", '
        '"content": "S01: these studies suggest"}}]}}\n')
    (tmp_path / "transcript-03.jsonl").write_text(
        use + '"name": "Read", "input": {"file_path": "C:\\\\tmp\\\\studies\\\\S02.md"}}]}}\n')
    assert hops_score.rereads(tmp_path) == 1  # hop 3 only


def test_the_scorer_imports_nothing_from_the_plugin():
    for name in ("hops_score.py", "hops_select.py", "hops_build.py"):
        source = (V2 / name).read_text(encoding="utf-8")
        assert "from qlaudified" not in source and "import qlaudified" not in source


# --- the runner ------------------------------------------------------------------------------

def test_runner_hops_suite(capsys):
    run = _run_module()
    assert run.main(["--suite", "hops", "--set", "dry", "--tasks", "hops-fam-a-n04",
                     "--repeats", "1", "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("2 runs planned")  # relay and session, off only
    steps = run.steps_for("hops-fam-a-n04", "relay", "hops")
    assert steps.count(run.NEW_SESSION) == 3 and len(steps) == 7


def test_new_session_steps_start_fresh_and_keep_every_artifact(tmp_path, monkeypatch):
    """``/new`` drops --resume; each session's transcript and the hops/ folder are kept."""
    run = _run_module()
    config = tmp_path / "config"
    monkeypatch.setitem(run.TEST_ENV, "CLAUDE_CONFIG_DIR", str(config))
    calls = []

    def fake(cmd, cwd, **_):
        calls.append(cmd)
        sid = cmd[cmd.index("--resume") + 1] if "--resume" in cmd else f"s{len(calls)}"
        (config / "projects" / "p").mkdir(parents=True, exist_ok=True)
        (config / "projects" / "p" / f"{sid}.jsonl").write_text("{}\n")
        (Path(cwd) / "hops" / f"{len(calls):02d}.md").write_text("S01: may\n")
        out = {"session_id": sid, "result": "ok", "total_cost_usd": 0.0, "num_turns": 1}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out).encode(), stderr=b"")

    monkeypatch.setattr(run.subprocess, "run", fake)
    record = run.run_one("hops-fam-a-n04", "relay", "off", "haiku", 10, tmp_path / "out", "hops")
    assert len(calls) == 4 and not any("--resume" in c for c in calls)
    assert record["sessions"] == ["s1", "s2", "s3", "s4"]
    assert sorted(p.name for p in (tmp_path / "out").glob("transcript-*")) == [
        f"transcript-{n:02d}.jsonl" for n in range(1, 5)]
    assert sorted(p.name for p in (tmp_path / "out" / "hops").iterdir()) == [
        ".keep", "01.md", "02.md", "03.md", "04.md"]
    calls.clear()
    record = run.run_one("hops-fam-a-n04", "session", "off", "haiku", 10, tmp_path / "out2", "hops")
    assert sum("--resume" in c for c in calls) == 3 and record["sessions"] == ["s1"]
