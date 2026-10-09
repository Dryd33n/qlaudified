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
  *Later the same day:* lazy imports done (see Benchmarks below).
- **One study repeat is now 216 runs** (27 tasks × 2 prompt styles × 4 conditions); the pilot sets
  how many repeats the budget allows.
- The free test suite takes ~80 s (from ~60 s): every tool call now runs the hook.

## Benchmarks (Oct 8, revision 2)

Machine under its usual background load (~20% CPU, Defender real-time scanning on), so absolute
numbers are noisy; comparisons are interleaved call by call.

- **Rule path (NFR-3, p95 <= 400 ms): met.** PostToolUse on `post_read`, 150 interleaved calls
  each: before 314 / 407 ms (p50 / p95), after 276 / 364 ms, revision 1 268 / 338 ms. The fix was
  imports: `dataclasses` (pulls in `inspect`, `ast`, `dis`, ~27 ms) is replaced on the hook path by
  `qlaudified/records.py`, and `traceback` (~15 ms) loads only when an error is logged. The floor
  is ~117 ms of Git Bash plus the `py` launcher before any of our code runs.
- **Wait-for-pending race fixed:** Stop's wait could stat a job file its finished job had just
  deleted and raise (seen once as a failing unit test under load).
- **Sidecar step (NFR-4, p95 <= 10 s): met on the evidence so far.** `scripts/bench_sidecar.py`
  replays the 14 recorded sessions with a fake backend: 24 of 31 tool steps meet the threshold
  (77%: the recordings are short and mostly reads), step prompts are 1.8k / 2.4k chars (p50 / p95),
  and the handler adds 29 / 45 ms around the call. One live haiku call on the median prompt:
  6.1 s, 4,317 input and 964 output tokens, $0.00135. Earlier `claude -p` probes ran 2.6–6.1 s, the
  slow one being the first, uncached call. Estimate: 0.36 + 0.05 + 6.1 = ~6.5 s.
- **Cost per qualifying step: ~$0.0013 on haiku** (one live call; the pilot measures it properly).
  Most input tokens are `claude -p`'s own overhead, not the ~460-token prompt, and output tokens
  (964 for a small JSON answer) cost more than input. A 20-step task at 77% qualifying is ~$0.02
  of sidecar calls.

## Live check and decay dry run (Oct 8)

- **Live task (`decay-finance-d5`, Medium, haiku): the "Done when" line holds.** Four prompts in
  one session, $0.023 for the agent. `provenance.csv` filled at steps 1–6 with origin, source
  qualifiers, first use and impact; six sidecar step calls took 3.8–4.7 s and ~$0.0005 each. The
  refeed reached Claude: its answer cited `[F1]` and `[F2, qualifier: pending]` and kept both
  hedges. A report was written at every Stop; no errors were logged.
- **Bug found live: digits in file names were figures.** "ops-1.md: Support closed 214 tickets in
  week 3." restates its fact word for word, but the verifier read the 1 in `ops-1.md` as an
  unsupported figure and called it contradicted (3 of 5 ops claims). The same digits turned the
  prompt "Read ops-1.md, ops-2.md, ops-3.md…" into a User Prompt fact, which then "supported" a
  claim through its 2. `text.clean` now drops bare file names that contain a digit, so the
  verifier and capture both skip them (use tracking already skipped paths).
- **The Stop report call is slow:** the Administrator's report call took 11–21 s (Stop p95 ~20 s
  in the dry run). No NFR covers it; worth a look if users notice the wait.
- **Decay dry run: 7 decay tasks × {low, medium} × natural × 1 repeat on haiku, ~$0.32 with sidecar calls, all 14
  runs finished and scored.** Qualifiers kept in the final answer: Medium 14/14, Low 10/14 (+29
  points, paired, over 7 tasks); kept at first use 8/14 vs 7/14. Low dropped one hedge at every
  distance (3/4 at 0, ~5 and ~15 steps, 1/2 after `/compact`); Medium dropped none. Every
  planted fact was in the ledger with the right qualifiers and origin, and the report flagged
  every drop. One repeat with 2–4 tasks per distance proves only that the pipeline works; the
  pilot decides whether the drop rate is high enough to study.
- `eval/score.py` crashed printing "−" to a cp1252 Windows console; it now writes `--out` first
  and prints UTF-8.

### Decay dry run: scorer output

`py -3 eval/score.py --runs <the 14 decay runs> --model haiku`, verbatim. No `off` runs, so no
overhead column; Consults is n/a in Low because nothing tells Claude about the CSV there.

#### haiku · natural prompts

| Condition | Runs | Qualifiers kept | Kept at first use | Uncaught drops | Ledger: facts / qualifiers / origin | Verifier accuracy | Consults | Cost per run | Overhead vs off | Sidecar $/row | PostToolUse p95 | Stop p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low | 7 | 71% (10/14) [57–86%] | 50% (7/14) | 0% (0/14) [0–0%] | 100% (14/14) / 100% (14/14) / 100% (14/14) | 100% (14/14) | n/a | $0.0226 | – | $0.00092 | 6392 ms | 20795 ms |
| medium | 7 | 100% (14/14) [100–100%] | 57% (8/14) | 0% (0/14) [0–0%] | 100% (14/14) / 100% (14/14) / 100% (14/14) | 100% (14/14) | 0% (0/7) | $0.0229 | – | $0.00090 | 6472 ms | 19563 ms |

Qualifiers kept by distance (decay tasks):

| Condition | 0 steps | ~5 steps | ~15 steps | ~15 + /compact |
| --- | --- | --- | --- | --- |
| low | 75% (3/4) | 75% (3/4) | 75% (3/4) | 50% (1/2) |
| medium | 100% (4/4) | 100% (4/4) | 100% (4/4) | 100% (2/2) |

Paired by task (b − a, 95% bootstrap interval over tasks):

- qualifiers kept, medium vs low on decay tasks at ~5 and ~15 steps: +30 points [+10, +50] over 5 tasks
- qualifiers kept, medium vs low: +29 points [+14, +43] over 7 tasks
- uncaught drops, medium vs low: +0 points [+0, +0] over 7 tasks
