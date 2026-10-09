# Sprints 5–6: the effectiveness study (protocol)

**Revision note (Oct 8, 2026, before any study run).** The first version of this protocol was
written for design revision 1 (rule-based capture, deltas, post-hoc vs Medium). The same day,
the design returned to its original idea (design.md, revision 2): the Provenance Administrator
sidecar records REQ-3.2 rows in every mode, and refeeding them is the hypothesis. This protocol
replaces the first version. No study run had been made, so no data informed the change. The
framework built for the first version (pressure prompts, resumable runner, bootstrap comparisons)
carries over.

The hypotheses, analysis and stopping rules below are fixed before the study runs; any later
change gets a dated note here, with its reason.

## Question

Does feeding the provenance record back into Claude's loop (Medium) keep qualifiers alive across
the steps of a task better than recording alone (Low), and at what token cost? Does High's retry
add to that? Is the record itself accurate?

## Why pressure prompts and decay tasks

- **Ceiling.** In the Sprint 4 dry run, Claude kept every qualifier with no plugin at all (6/6) on
  natural prompts. Each task has a pressure prompt (a slide line, a table, a headline, an
  executive summary) where models tend to drop qualifiers.
- **Decay.** The original tasks put the answer 1–3 steps after the read. Decay tasks read a hedged
  fact at step 1 and ask for it 0, ~5 or ~15 steps later (other reads, a calculation, later
  turns), and one variant compacts midway. Refeeding should matter most where the fact is far
  from the answer.

## Design

- **Conditions:** Off (no plugin), Low (record only: the sidecar builds the ledger and report,
  nothing reaches Claude), Medium (record + refeed), High (+ one retry).
- **Tasks:** the 20 corpus tasks (natural and pressure prompts) and about 6 decay tasks at three
  distances (built in Sprint 5).
- **Models:** Sonnet is the headline; haiku is a smaller cross-check. The sidecar is haiku.
- **Runs:** `eval/run.py`, isolated `claude -p` per run, recorded, resumable, on plan usage plus
  extra credits.

## Measures (`eval/score.py`)

| Measure | Definition |
| --- | --- |
| **Qualifiers kept (final)** | Hedged ground-truth facts the final answer states with the source's strongest hedge class |
| **Decay curve** | For each hedged fact, whether its qualifier was present at first use, at each later use, and in the final answer (from the ledger's use tracking and the answer) |
| Uncaught drops | Drops in the final answer that the report did not flag (Off flags nothing) |
| **Ledger accuracy** | Recall of planted critical facts as rows; source qualifiers correct; origin correct where the corpus makes it unambiguous |
| Verifier accuracy | Report verdicts (kept vs dropped vs contradicted vs unsupported) against ground truth |
| Consults | Runs where Claude read `provenance.csv`, the first step it did, and the size read |
| Cost | Per run (`total_cost_usd` plus `usage.jsonl`), overhead vs Off paired by task, cost per ledger row |
| Latency | Rule path and sidecar step p95, Stop p95 |

Every final answer is also re-checked offline by the rules, so conditions are judged alike.

## Hypotheses (pre-registered)

Comparisons are paired by task, reported as b − a with a 95% bootstrap interval resampling tasks
(2,000 resamples, seed 7). A hypothesis holds when its interval excludes 0 in the predicted
direction. Results are reported per model and per prompt variant.

- **H1 (headline):** on decay tasks at ~5 and ~15 steps, Medium keeps more qualifiers in the final
  answer than Low.
- **H2:** in Low, qualifiers kept falls with distance; Medium's fall is smaller (the difference in
  slope between 0 and ~15 steps).
- **H3:** recording alone doesn't change answers: Low and Off differ by less than 10 points in
  qualifiers kept (an equivalence check).
- **H4:** High keeps more qualifiers than Medium.
- **H5:** the ledger is accurate: at least 90% of planted hedged facts appear as rows with the
  right source qualifiers; at least 80% correct origin where unambiguous.
- **H6:** verifier accuracy is at least 90% on Sonnet runs.
- **Cost:** report Medium's and High's overhead against Off, and cost per row; NFR-1 and NFR-2
  targets are set from the pilot, before the Sonnet runs.

Null and negative results are reported as they come, in the README too.

## Budget and order (about $25 of plan usage and extra credits)

| Stage | Runs | Purpose |
| --- | --- | --- |
| 1. Pilot (haiku) | ~30: a few tasks in every mode, plus the decay tasks under Low | Cost per row and per run; drop rate on decay tasks (go/no-go); set NFR-1 and NFR-2 |
| 2. Sonnet, repeat 1 | All tasks, both variants, all conditions | Real cost per run; first full pass |
| 3. Sonnet, more repeats | As the budget allows, in order | Precision |
| 4. Haiku cross-check | Same design, fewer repeats | Does the effect hold on a weaker model? |

The run count is set after the pilot measures cost per run with the sidecar on (Sprint 4 measured
$0.092 for one Sonnet run without it). Rules fixed now:

- **Go/no-go after the pilot:** if Low drops fewer than 20% of stated hedged facts on the decay
  and pressure tasks, the tasks are made harder (and this file notes how) before any Sonnet run.
- **Repeats are added in order and never chosen by their results.** If the budget runs out, the
  study stops at the last complete repeat.
- **Failed runs** (non-zero exit: limits, crashes) are rerun; no run or task is dropped for its
  result.
- `--daily-cap` keeps each day inside plan limits; the runner stops at the first usage-limit error
  and resumes on the next invocation.

## Threats to validity

- **Lexical scoring:** a paraphrase that keeps the meaning in different words ("may change" for
  "subject to change") counts as a drop, in scoring and in the rule checks alike.
- **The sidecar judges itself:** origin and impact fields are the sidecar's judgments; ground
  truth exists only where the corpus makes them unambiguous.
- **Synthetic corpus written by the same author** as the plugin and the prompts.
- **Pressure and decay are designed to cause drops:** they measure behavior under stress, not the
  everyday base rate; natural prompts cover that.
- **Plan-usage costs** are Claude Code's `total_cost_usd` estimates, not invoices.
- **Reasoning text comes from the transcript,** whose format can change between versions.

## Build notes (Oct 8, revision 2)

Built and tested offline (285 free tests; ruff and mypy clean). Issues #41–#49.

| Piece | Where |
| --- | --- |
| Facts, not passages; sources log with hashes | `capture.read_tool_result`, `store.sources` |
| Steps, Claude's reasoning from the transcript, use tracking, Claude's own claims | `store.next_step`, `transcript.py`, `tracking.py` |
| User prompt and provided files | `hooks/user_prompt_submit.py` |
| The Provenance Administrator (step call and final report call) | `administrator.py` |
| Rolling read-only `provenance.csv`, `claims.csv` | `store.export_csv` |
| Refeed: session line, deltas with the CSV path, digest, consults | `inject.py`, `hooks/session_start.py`, `hooks/post_tool_use.py` |
| Verification on facts plus source re-reads; report with the ledger | `verify/__init__.py`, `report.py`, `hooks/stop.py` |
| Decay tasks (7) and pressure prompts | `tests/sandbox/decay-*`, `eval/tasks/decay-*.toml` |
| Runner and scorer for off / low / medium / high | `eval/run.py`, `eval/score.py` |

**One live check (Medium, haiku, `seed-hedged`, $0.007 in total):** the ledger filled at the Read
step (3 rows, Provided Document, source qualifiers right); the Administrator's step call took
4.5 s and $0.00057; Stop verified both claims, recorded each fact's final use with its qualifiers,
and the report call wrote impacts and a summary (10.4 s, $0.0017, 1,865 output tokens). No errors.
The report call's length and its first-person summary were then capped and fixed (at most 20
words per impact, 60 for the summary, third person); not yet re-measured live.

Found while building:

- **Thinking arrives empty in `claude -p`** (redacted), so "reasoning" is Claude's visible text
  between tool calls plus its tool inputs. Uses inside private thinking can't be seen.
- **A shared figure isn't a shared topic.** "Revenue grew 12% from Q2" matched a filler line, "The
  data team runs 12 nightly jobs", as clean support, because the number counted as a shared word.
  Topic overlap now ignores numbers, in the verifier and in use tracking (found by the decay tasks'
  answer-key test).
- **Facts are short, so topic overlap runs both ways:** the better of claim-covers-fact and
  fact-covers-claim.
- **A hedge belongs to its own clause** in uses and final-answer uses too: in "revenue was $4.2M,
  so per head that's about $87.5K", "about" qualifies $87.5K, and $87.5K is recorded as Claude's
  own claim.
- **Paths and IDs aren't figures** ("tmp6cqrmw", "toolu_01…") when looking for Claude's claims.
- **The rule path misses NFR-3:** PostToolUse p95 is 360–390 ms through the real hook command
  (p50 315–340 ms), against 300 ms and revision 1's 234 ms. The extra ~120 ms is step numbering,
  the sources log, the transcript read, use tracking and the CSV rewrite (one SQLite connection per
  hook call already saved ~30 ms). Steps that change nothing skip the CSV rewrite (Glob step: p95
  317 ms). Rewriting a new read-only file can also draw an antivirus scan: one benchmark run had a
  2.5 s p95. Time is the accepted cost in revision 2, so NFR-3 is revised to 400 ms; lazy imports
  are the next lever if it matters.
- **One study repeat is now 216 runs** (27 tasks × 2 prompt styles × 4 conditions); the pilot sets
  how many repeats the budget allows.
- The free test suite takes ~80 s (from ~60 s): every tool call now runs the hook.
