"""Carry-over of qualified facts across sessions (RFD-5): match, budget, once per session, hooks."""

import json

from qlaudified import carry, paths
from qlaudified.hooks import session_start, user_prompt_submit
from qlaudified.store import Span, Store

ABSTRACTS = [  # (intervention, outcome, result sentence, qualifiers)
    ("Yoga", "fatigue", "Yoga may have reduced fatigue by about 32% compared with usual care.",
     "may; about"),
    ("Yoga", "fatigue", "Yoga appeared to reduce fatigue by roughly 38% relative to controls.",
     "appeared; roughly"),
    ("Acupuncture", "chronic pain", "Acupuncture might reduce chronic pain by up to 35%.",
     "might; up to"),
    ("Hearing aids", "cognitive decline",
     ("Hearing aids cut cognitive decline by 28% relative to controls."), ""),
    ("Tai chi", "falls", "In the tai chi group, falls possibly fell by an estimated 20%.",
     "possibly; estimated"),
]
REPORT = ("## Yoga\n\nYoga reduces fatigue by 36.33% (pooled across 6 studies).\n\n"
          "## Acupuncture\n\nAcupuncture reduces chronic pain by 33.17%.\n\n"
          "## Hearing aids\n\nHearing aids reduce cognitive decline by 28%.\n")


def _earlier(project, session="earlier"):
    store = Store(project / ".claude" / ".qlaudified" / "sessions" / session)
    for n, (_, _, text, qualifiers) in enumerate(ABSTRACTS, 1):
        store.add_span(Span("", "local-doc", f"abstracts/A{n:03d}.md", "L10", text,
                            qualifiers=qualifiers, hash=f"h{n}"))
    store.close()


def _payload(project, session="now", **extra):
    return {"session_id": session, "cwd": str(project), **extra}


def test_earlier_facts_are_the_qualified_ones_read_from_sources(tmp_path):
    _earlier(tmp_path)
    facts = carry.earlier_facts("now", _payload(tmp_path))
    assert sorted(f.source for f in facts) == ["abstracts/A001.md", "abstracts/A002.md",
                                                "abstracts/A003.md", "abstracts/A005.md"]
    assert carry.earlier_facts("earlier", _payload(tmp_path, "earlier")) == []  # not its own


def test_a_report_gets_one_line_per_named_hedged_finding_first(tmp_path):
    _earlier(tmp_path)
    facts = carry.earlier_facts("now", _payload(tmp_path))
    picked = carry.pick(facts, REPORT, budget_chars=10_000)
    first_two = {f.text.split()[0] for f in picked[:2]}
    assert first_two == {"Yoga", "Acupuncture"}  # coverage before a second Yoga line
    assert "Tai" not in " ".join(f.text for f in picked)  # not named in the report
    tight = carry.pick(facts, REPORT, budget_chars=len(carry.HEADER) + 200)
    assert len(tight) == 1


def test_carry_sends_each_fact_once_per_session_with_its_qualifiers(tmp_path):
    _earlier(tmp_path)
    text = carry.carry("now", REPORT, 1200, _payload(tmp_path))
    assert text.startswith(carry.HEADER)
    assert "source says: may, about" in text and "abstracts/A003.md" in text
    assert carry.carry("now", REPORT, 1200, _payload(tmp_path)) == ""  # already sent
    assert carry.carry("other", REPORT, 0, _payload(tmp_path, "other")) == ""  # budget 0: off


def test_placebo_masks_the_qualifiers(tmp_path):
    _earlier(tmp_path)
    text = carry.carry("now", REPORT, 1200, _payload(tmp_path), placebo=True)
    assert "abstracts/A001.md" in text and "source says" not in text
    assert " may " not in text and "about" not in text


def test_no_match_and_no_earlier_sessions_add_nothing(tmp_path):
    assert carry.carry("now", REPORT, 1200, _payload(tmp_path)) == ""
    _earlier(tmp_path)
    assert carry.carry("now", "Write a haiku about autumn leaves.", 1200, _payload(tmp_path)) == ""


def test_prompt_hook_carries_facts_in_medium_but_not_low(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    _earlier(tmp_path)
    out = user_prompt_submit.handle(_payload(tmp_path, prompt=f"Here's our report:\n\n{REPORT}"))
    context = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "Yoga may have reduced fatigue" in context
    (tmp_path / ".claude" / ".qlaudified" / "config.toml").write_text('mode = "low"\n')
    assert user_prompt_submit.handle(_payload(tmp_path, "later", prompt=REPORT)) is None


def test_session_start_says_earlier_ledgers_hold_qualified_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    first = session_start.handle(_payload(tmp_path, "first", source="startup"))
    assert "Earlier sessions" not in first["hookSpecificOutput"]["additionalContext"]
    _earlier(tmp_path)
    out = session_start.handle(_payload(tmp_path, source="startup"))
    lines = out["hookSpecificOutput"]["additionalContext"].splitlines()
    assert "provenance.csv" in lines[0]
    assert lines[1].startswith("Earlier sessions in this project (2) recorded 4 facts")


def test_a_damaged_earlier_ledger_is_skipped(tmp_path):
    _earlier(tmp_path)
    bad = tmp_path / ".claude" / ".qlaudified" / "sessions" / "broken"
    bad.mkdir()
    (bad / "index.sqlite").write_bytes(b"not a database")
    assert len(carry.earlier_facts("now", _payload(tmp_path))) == 4
    assert json.loads(json.dumps(paths.safe_name("now"))) == "now"
