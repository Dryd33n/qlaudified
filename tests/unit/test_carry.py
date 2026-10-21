"""Carry-over of critical facts across sessions (RFD-5): match, budget, once per session, hooks."""

from qlaudified import carry
from qlaudified.hooks import session_start, user_prompt_submit
from qlaudified.store import Span, Store

ABSTRACTS = [  # (origin, result sentence, numbers, qualifiers)
    ("local-doc", "Yoga may have reduced fatigue by about 32% compared with usual care.", "32%",
     "may; about"),
    ("local-doc", "Yoga appeared to reduce fatigue by roughly 38% relative to controls.", "38%",
     "appeared; roughly"),
    ("local-doc", "Acupuncture might reduce chronic pain by up to 35%.", "35%", "might; up to"),
    ("local-doc", "Hearing aids cut cognitive decline by 28% relative to controls.", "28%", ""),
    ("local-doc", "In the tai chi group, falls possibly fell by an estimated 20%.", "20%",
     "possibly; estimated"),
    ("local-doc", "Adults were randomised to hearing aids or usual care.", "", ""),  # no fact
    ("claude", "Hearing aids cut cognitive decline by 28%, so fund them.", "28%", ""),  # its own
]
REPORT = ("## Yoga\n\nYoga reduces fatigue by 36.33% (pooled across 6 studies).\n\n"
          "## Acupuncture\n\nAcupuncture reduces chronic pain by 33.17%.\n\n"
          "## Hearing aids\n\nHearing aids reduce cognitive decline by 28%.\n")
FIRM = "Hearing aids cut cognitive decline by 28% relative to controls."


def _earlier(project, session="earlier"):
    store = Store(project / ".claude" / ".qlaudified" / "sessions" / session)
    for n, (origin, text, numbers, qualifiers) in enumerate(ABSTRACTS, 1):
        store.add_span(Span("", origin, f"abstracts/A{n:03d}.md", "L10", text, numbers=numbers,
                            qualifiers=qualifiers, hash=f"h{n}"))
    store.close()


def _payload(project, session="now", **extra):
    return {"session_id": session, "cwd": str(project), **extra}


def test_earlier_facts_are_the_critical_ones_read_from_sources_hedged_or_firm(tmp_path):
    _earlier(tmp_path)
    facts = carry.earlier_facts("now", _payload(tmp_path))
    assert sorted(f.source for f in facts) == [f"abstracts/A{n:03d}.md" for n in range(1, 6)]
    assert FIRM in [f.text for f in facts]  # firm facts are carried too
    assert carry.earlier_facts("earlier", _payload(tmp_path, "earlier")) == []  # not its own


def test_a_report_gets_one_line_per_named_finding_first(tmp_path):
    _earlier(tmp_path)
    facts = carry.earlier_facts("now", _payload(tmp_path))
    picked = carry.pick(facts, REPORT, budget_chars=10_000)
    first_three = {f.text.split()[0] for f in picked[:3]}
    assert first_three == {"Yoga", "Acupuncture", "Hearing"}  # coverage before a second Yoga line
    assert "tai chi" not in " ".join(f.text for f in picked)  # not named in the report
    tight = carry.pick(facts, REPORT, budget_chars=len(carry.HEADER) + 110)
    assert len(tight) == 1


def test_carry_sends_hedged_and_firm_facts_once_per_session(tmp_path):
    _earlier(tmp_path)
    text = carry.carry("now", REPORT, 1200, _payload(tmp_path))
    assert text.startswith(carry.HEADER)
    assert "source says: may, about" in text and "abstracts/A003.md" in text
    firm = next(ln for ln in text.splitlines() if "A004" in ln)
    assert FIRM in firm and "source says" not in firm  # stated in its source's own words
    assert carry.carry("now", REPORT, 1200, _payload(tmp_path)) == ""  # already sent
    assert carry.carry("other", REPORT, 0, _payload(tmp_path, "other")) == ""  # budget 0: off


def test_a_long_source_label_is_cut_in_the_carried_line_only():
    command = '$ cd "C:/Users/someone/AppData/Local/Temp/run-1234/project" && cat abstracts/*.md'
    span = Span("F7", "command-output", command, "p2", "Yoga cut fatigue by 40%.", numbers="40%")
    line = carry.line_for(span)
    assert line.startswith("[F7 $ cd ") and "…" in line and "cat abstracts" not in line
    assert line.endswith("Yoga cut fatigue by 40%.") and span.source == command


def test_placebo_masks_the_qualifiers_and_leaves_firm_lines_alone(tmp_path):
    _earlier(tmp_path)
    text = carry.carry("now", REPORT, 1200, _payload(tmp_path), placebo=True)
    assert "abstracts/A001.md" in text and "source says" not in text
    assert " may " not in text and "about" not in text
    assert FIRM in text


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
    assert "Yoga may have reduced fatigue" in context and FIRM in context
    (tmp_path / ".claude" / ".qlaudified" / "config.toml").write_text('mode = "low"\n')
    assert user_prompt_submit.handle(_payload(tmp_path, "later", prompt=REPORT)) is None


def test_session_start_says_earlier_ledgers_hold_critical_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    first = session_start.handle(_payload(tmp_path, "first", source="startup"))
    assert "Earlier sessions" not in first["hookSpecificOutput"]["additionalContext"]
    _earlier(tmp_path)
    out = session_start.handle(_payload(tmp_path, source="startup"))
    lines = out["hookSpecificOutput"]["additionalContext"].splitlines()
    assert "provenance.csv" in lines[0]
    assert lines[1].startswith("Earlier sessions in this project (2) recorded 5 critical facts "
                               "from sources (4 with qualifiers)")


def test_a_damaged_earlier_ledger_is_skipped(tmp_path):
    _earlier(tmp_path)
    bad = tmp_path / ".claude" / ".qlaudified" / "sessions" / "broken"
    bad.mkdir()
    (bad / "index.sqlite").write_bytes(b"not a database")
    assert len(carry.earlier_facts("now", _payload(tmp_path))) == 5
