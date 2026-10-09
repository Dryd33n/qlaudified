# Study protocol v2 (draft, Oct 9, 2026)

Replaces the study design in [sprint-5.md](sprint-5.md) after the
[methods critique](methods-critique.md). Everything run under the old design (Sprint 4–5 dry runs,
the Oct 9 pilot, the stopped haiku repeat) is **exploratory** and stays out of every confirmatory
table.

**Status: draft.** The pilot fills in the parameters marked *(set after the pilot)*. Then the
protocol is frozen: committed, tagged `protocol-v2-frozen` and pushed, so GitHub records when it
became public. Confirmatory runs start only after the tag, and are analysed with the code at that
tag.

## Question and claim

In Claude Code, does feeding a source's qualifiers back into the agent's context (Medium) make its
answers state facts **with the certainty the source gave them** more often than the cheapest
alternatives? And does it do so without making firm facts sound uncertain?

The claim is limited to Claude Code, to the model(s) run and to this author-written corpus. It is
not a claim about how often qualifiers are lost in everyday use.

## Conditions

| Condition | Plugin | What reaches Claude |
| --- | --- | --- |
| off | none | nothing |
| prompt | none | one appended system line: *"When you state a figure from a source, keep the source's qualifiers."* |
| rules | Medium, `backend = "none"` | refeed of rule-built rows; no Administrator calls |
| placebo | Medium, `refeed = "placebo"` | the same refeed lines with the qualifiers masked out (plugin lexicon words and the row's recorded qualifiers) |
| medium | Medium | refeed lines with qualifiers |
| low *(secondary)* | Low | nothing (records only) |
| high *(exploratory)* | High | Medium plus one retry |

Medium and placebo share the session-start line and the CSV path. They differ only in whether the
refeed carries the hedge. That separates "a reminder of the fact" from "a reminder of its hedge".
Rules vs Medium isolates the Administrator. Prompt vs Medium is the primary contrast. High is
analysed only on tasks where Medium is seen to drop a hedge; otherwise its retry has nothing to do.

## Tasks

Built by `eval/v2/build.py` from `eval/v2/families/*.toml`. The task set is frozen by
`eval/v2/MANIFEST.json`, and a unit test fails if the built files differ from it.

- **16 families** across four fictional organisations (clinical operations, logistics, a council
  and a software company): 77 facts in total, 33 of them hedged.
- **Every family mixes hedged and firm facts of the same type** (a Q2 actual next to a Q3
  estimate), so over-hedging and hedge leakage can be seen.
- **Hedge placement varies:** in the sentence (4 families), a heading (3), a footnote (3), a table
  cell (3), or a second document the first one cites (3). Hedges are often paraphrases ("subject to
  the finance team's quarter-end review", "not yet final", "indicative only").
- **Open questions** name a topic, not a fact ("write a short update for the board on the trial").
- **Two distances:** *near* (the question comes right after reading) and *far* (eight distractor
  documents read two at a time, then a ~700-word operating report full of figures, then the
  question). Distance is **measured in tokens** from each run's transcript: the context growth
  between the last read of a source and the answer.
- **Three prompt styles**, analysed separately:
  - *natural*: the question alone.
  - *format*: the question plus a format constraint (a two-column table, or one slide line).
  - *antihedge*: the format constraint plus "State the figures plainly, with no hedging".

  For antihedge prompts, calibration and obeying the user conflict by design, so they're reported
  apart from the primary test.

## Outcomes

Scored per fact by `eval/v2/calib.py`. The scope rules are in its docstring and are part of this
protocol.

- **Primary, calibration:** of the facts an answer states, the share stated with the source's
  certainty (a hedged fact with a hedge, a firm fact plainly).
- **Secondary:**
  - *stated rate*: facts stated, out of all facts.
  - *hedged kept*, and its complement *inflated*: among stated hedged facts.
  - *over-hedging*: firm facts stated with a hedge.
  - *format compliance*.
  - *re-read rate*: Claude reopened a source after the question.
  - *distance in tokens*.
  - *tokens per run by component*: agent input, cached and output, plus sidecar input and output.
  - *PostToolUse and Stop latency*.
- **Harms are reported in the same table as the benefit:** over-hedging, compliance, latency and
  tokens.

Plugin citation markers (`[F1]`, `[F2, qualifier: pending]`) are removed before scoring in every
condition, so Medium gets no credit for a hedge that appears only in its own citations. One hedge
of any strength counts as kept; strengths are not compared.

## Scorers and validation

1. **Rule scorer** (`calib.py`, `cues.py`, `figures.py`): imports nothing from the plugin. Its cue
   list was written separately from the plugin's lexicon. A unit test enforces the independence.
2. **LLM judge** (`judge.py`, sonnet by default): sees only the answer, with markers stripped, and
   what each source says, with the facts shuffled. It never sees the condition.
3. **Human labels** (`labels.py`): 40–60 items, balanced between hedged and firm facts, with
   markers stripped and shuffled, labelled without the key. Cohen's κ is computed for each scorer
   against them.

**Which scorer is primary** is decided by the labels, under a rule fixed now: the rule scorer, if
its κ against the human labels is at least 0.6; otherwise the judge, if its κ is at least 0.6;
otherwise both are reported and the study is called exploratory.

## Analysis

- **Unit: the task family.** Each contrast is a list of per-family differences in the outcome
  rate, pooled over near and far, natural and format prompts, and repeats.
- **Primary test:** calibration, medium vs prompt. Two-sided sign-flip permutation test over
  families (exact up to 16 families), α = 0.05. The effect is reported as the mean difference in
  points, with a family-bootstrap 95% interval as a description.
- **Smallest effect of interest:** 15 points.
- **Secondary contrasts,** Holm-adjusted:
  - calibration, medium vs placebo
  - calibration, medium vs rules
  - calibration, prompt vs off
  - calibration, medium vs off
  - over-hedging of firm facts, medium vs off
- **Sensitivity check:** an exact McNemar test on paired facts (same fact, task, style and repeat
  in both conditions).
- **Low vs off,** if run, is an equivalence check: the 90% interval inside ±10 points.
- **Everything else is descriptive or exploratory:** distance breakdowns, scope types, antihedge
  prompts, High, and the second model.

## Sample size

Set by power, not by budget. `eval/v2/power.py` simulates the primary test using the pilot's
family-level rates. The confirmatory design is the smallest one with **at least 80% power for 15
points**. If 16 families aren't enough at an affordable number of repeats, more families are
written, and frozen, **before any confirmatory run**. If no affordable design reaches 80%, the
study is run as planned and labelled underpowered. *(Repeats, families and model: set after the
pilot.)*

## Runs, exclusions and hygiene

- **Separate folders.** Runs go to `eval/runs/{dry,pilot,confirmatory}/v2/`. Only `confirmatory`
  enters the results, and pilot runs are never reused.
- **Model:** fixed at the freeze. The pilot's cost per run decides between Sonnet and haiku, and
  the other model, if run, is secondary. *(Set after the pilot.)*
- **Order:** repeat-major, with conditions innermost. Repeats are added in order and never chosen
  by their results. If the budget runs out, the study stops at the last complete repeat.
- **Failed and invalid runs:**
  - A run that exits non-zero (limits, crashes) is rerun.
  - A run that exits 0 with an empty answer is retried once at once. If it's still empty, it's
    kept, marked invalid and scored as stating nothing.
  - No run is dropped for its content.
- **Re-reads are allowed** and reported, not excluded.
- **Blinding:** human labelling uses the stripped, shuffled sheet without the key. The judge never
  sees conditions.

## Pilot (before the freeze)

Purpose:
- check that the tasks produce drops at all (off and prompt must lose some hedges);
- check that the scorers agree with each other on real answers;
- measure cost per run and the run-to-run variance for the power calculation.

Proposed size: 8 families (two per organisation, covering all five hedge placements), far tasks,
natural, format and antihedge prompts, conditions off, prompt, placebo and medium, one repeat. Then
40–60 human labels on pilot answers, κ, power, and the freeze.

**Ceiling gate (added after the Oct 9 dry run, before any pilot run):** if off keeps at least 90%
of stated hedged facts under natural and format prompts, the tasks are too easy to show an effect.
They are then made harder before the freeze, with longer distances, a `/compact` step and more
competing figures, and re-piloted. The dry run (14 runs, no drops in any condition) suggests this
is likely.

## Known limitations (stated, not fixed)

- **Author-written, synthetic corpus.** No held-out set was written by someone else, and there are
  no real-document tasks yet.
- **Same-family judge.** The judge is a Claude model (no different-family judge). Human labels are
  the check.
- **Claude Code only;** no non-Claude agent.
- **Thinking is redacted in `claude -p`,** so where in a run a hedge was lost is known only from
  visible text.
- **Stress tasks, not base rates.**
