# Sprint 5: the effectiveness study (protocol)

Written on Oct 8, 2026, before any study run. The hypotheses, analysis and stopping rules below
are fixed now so the results can't steer them; any change gets a dated note here, with its reason.

## Question

Does re-injecting provenance during a run (Medium) prevent and catch dropped qualifiers better
than checking only afterwards (post-hoc), and what does it cost? High adds a background sidecar and
one retry at Stop: is that worth its extra cost?

## Why pressure prompts

In the Sprint 4 dry run, Claude kept every qualifier with no plugin at all (6/6), so natural
prompts leave nothing to measure: a ceiling effect. Each task now has two prompts:

- **natural** (`prompt.txt`): the everyday question.
- **pressure** (`prompt-pressure.txt`): the same question under a realistic constraint, one of four
  styles per task type: a slide line, a markdown table, a headline ("no hedging"), or a direct
  executive summary. The retry demo showed this kind of constraint makes models drop qualifiers.

## Design

- **Tasks:** the 20 corpus tasks (4 each of single-hop, multi-hop, conflicting sources, compaction,
  no-source), local files only, ground truth in `eval/tasks/*.toml`.
- **Conditions:** off (Low mode: nothing reaches Claude), post-hoc (the off runs verified offline),
  medium, high. Post-hoc needs no runs of its own.
- **Models:** Sonnet is the headline; haiku is a smaller cross-check.
- **Runs:** `eval/run.py`, isolated `claude -p` per run, recorded, resumable, on plan usage.

## Measures (`eval/score.py`)

The unit is a hedged ground-truth fact that the answer states.

- **Uncaught drops (headline):** the share of stated hedged facts whose qualifier was dropped and
  not flagged to the user. In off, every drop is uncaught.
- **Qualifiers kept:** the share stated with the source's strongest hedge class.
- **Verifier accuracy**, **attribution precision/recall**, **cost per run** (`total_cost_usd` plus
  `usage.jsonl`), **overhead vs off** (paired by task), **hook and Stop p95**.

Every answer is re-verified offline with the same rules (tier 1; NLI off), so conditions are
judged alike; the live verdicts users saw are kept in each run's store.

## Hypotheses (pre-registered)

All comparisons are paired by task, reported as b − a with a 95% bootstrap interval resampling
tasks (2,000 resamples, seed 7). A hypothesis holds when its interval excludes 0 in the predicted
direction. Results are reported per model and per prompt variant.

- **H1 (headline):** Medium has fewer uncaught drops than post-hoc.
- **H2:** Medium keeps more qualifiers than off (prevention, not just detection).
- **H3:** High keeps more qualifiers than Medium.
- **H4:** Verifier accuracy is at least 90% on Sonnet runs.
- **Cost:** Medium's overhead is at most 10% (NFR-1) and High's at most 20% (NFR-2) on Sonnet.

Null and negative results are reported as they come, in the README too.

## Budget and order (about $25 of plan usage and extra credits)

| Stage | Runs | Estimate |
| --- | --- | --- |
| 1. Pilot: haiku, pressure, off only, 1 repeat | 20 | ~$0.10 |
| 2. Sonnet, repeat 1, both variants, all conditions | 120 | ~$5–10 |
| 3. Sonnet, repeats 2 and 3 | 240 | ~$10–20 |
| 4. Haiku cross-check, 2 repeats | 240 | ~$1 |

One Sonnet run cost $0.092 on Oct 8 (mostly writing Claude Code's system prompt to the cache);
back-to-back runs should reuse it, so stage 2 measures the real cost per run before stage 3.

Rules fixed now:
- **Go/no-go after the pilot:** if off drops fewer than 20% of stated hedged facts under pressure,
  the pressure prompts are strengthened (and this file notes how) before any Sonnet run.
- **Repeats are added in order (r2, then r3) and never chosen by their results.** If the budget runs
  out, the study stops at the last complete repeat.
- **Failed runs** (non-zero exit: limits, crashes) are rerun; no run or task is dropped for its
  result.
- `--daily-cap` keeps each day's spend inside plan limits; the runner also stops at the first
  usage-limit error and resumes on the next invocation.

## Commands

```
py -3 eval/run.py --model haiku --variants pressure --conditions off --repeats 1 --daily-cap 1   # 1
py -3 eval/run.py --model sonnet --repeats 1 --daily-cap 8                                       # 2
py -3 eval/run.py --model sonnet --repeats 3 --daily-cap 8      # 3: resumes, adds r2 and r3
py -3 eval/run.py --model haiku --repeats 2 --daily-cap 2                                        # 4
py -3 eval/score.py --model sonnet --out docs/findings/data/results-sonnet.md
```

## Threats to validity

- **Lexical scoring:** a paraphrase that keeps the meaning in different words ("may change"
  for "subject to change") counts as a drop, in scoring and in the verifier alike.
- **Synthetic corpus written by the same author** as the plugin and the pressure prompts.
- **Small facts, short files:** real documents are longer and messier.
- **Plan-usage costs** are Claude Code's `total_cost_usd` estimates, not invoices.
- **Haiku sidecar on a haiku primary** inflates High's relative cost (Sprint 4); Sonnet is the
  fair test.
