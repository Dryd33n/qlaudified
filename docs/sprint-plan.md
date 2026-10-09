# Sprint plan

Seven one-week sprints take qlaudified from a hook spike to a tagged, evaluated v1 on Nov 22, 2026. Sprints 0–4 built design revision 1; Sprint 5 rebuilds the core around the Provenance Administrator (revision 2), and Sprint 6 runs the study.

> Exported from the living design doc. See `design.md` for requirement IDs and `testing.md` for the test setup.

## Overview

Medium mode is usable daily by the end of Sprint 2; everything after adds depth, High mode and evidence. A small seed corpus starts in Sprint 2 as test fixtures, so the eval doesn't start from zero in Sprint 4.

| Sprint | Dates (2026) | Goal | Demo at the end |
| --- | --- | --- | --- |
| 0 | Oct 9–11 | Prove the hooks behave as the design assumes | Findings note; go/no-go on inline markers |
| 1 | Oct 12–18 | Plugin skeleton, mode command, capture into the store | A session fills `provenance.csv` from local docs and code |
| 2 | Oct 19–25 | Medium mode end to end | Dropped qualifier caught and reported on a real task |
| 3 | Oct 26–Nov 1 | Web sources, NLI and LLM tiers | WebFetch summary diffed against the raw page |
| 4 | Nov 2–8 | High mode and the eval harness | One forced retry fixes a claim; runner scores 20 tasks |
| 5 | Nov 9–15 | The Provenance Administrator (design revision 2) | A live task fills `provenance.csv` step by step; Medium refeeds it |
| 6 | Nov 16–22 | Study, README, v1 tag | Decay curves and the Medium-vs-Low result in the README |

## Sprint 0 · Spike (Oct 9–11)

Goal: confirm the four hooks give us what the design depends on, before writing real code. Throwaway scripts that log stdin to a file are enough.

- [x] Log raw `PostToolUse` payloads for `Read`, `Grep`, `Bash`, `WebFetch`, `WebSearch` and one MCP tool; note where text, paths and line numbers appear
- [x] Confirm `additionalContext` from `PostToolUse` reaches Claude, and check how a factual provenance line is treated
- [x] Test `MessageDisplay`: batch sizes, latency, and whether markers can be added from span matching alone
- [x] Test `SessionStart` with the `compact` matcher after a manual `/compact`
- [x] Run a nested `claude -p` from a hook with `--safe-mode`, check it uses the Pro login; measure startup time and pick the default small model
- [x] Run every probe on Windows (exec form, `python`, backslash paths) and on macOS
- [x] Check the name qlaudified on GitHub and PyPI
- [x] Time Python hook startup on Windows (`python` vs `py -3`) and confirm a separate `CLAUDE_CONFIG_DIR` keeps its login

**Done when:** a short findings note and 4–6 recorded real sessions for the simulator are in the repo, and each risk in the design doc is marked confirmed, changed or retired.

## Sprint 1 · Foundations and capture (Oct 12–18)

Goal: a plugin that installs cleanly, remembers its mode, and records every local retrieval as spans. Nothing is injected or verified yet.

- [x] Repo, `pyproject.toml`, plugin manifest, `hooks.json` with the shell-form `py -3` / `python3` fallback (design.md, Hook command), MIT license
- [x] `config.toml` loading with defaults; `/qlaudified mode` with a session override (MOD-1 to MOD-3)
- [x] Session store: SQLite schema for spans and claims, CSV export, auto-created `.gitignore`
- [x] Capture hook for `Read`, `Grep` and Bash output: source, locator, hash, agent ID (CAP-1, CAP-6)
- [x] Span indexer: number, date and unit normalization; hedge lexicon v0 (CAP-2)
- [x] Error handling: every hook catches, logs, and exits cleanly (NFR-7)
- [x] Unit tests for normalization and the lexicon; CI on Windows and macOS (NFR-6)

**Done when:** a real session on a notes folder and a repo produces a correct `provenance.csv`, and capture adds under 300 ms per call.

## Sprint 2 · Medium mode end to end (Oct 19–25)

Goal: the core loop works with zero model calls: inject deltas, verify with rules, show the result. This is the sprint where qlaudified becomes useful.

- [x] Delta re-injection with the per-call character budget (INJ-1, INJ-2)
- [x] Compaction digest via `SessionStart` `compact` (INJ-3)
- [x] Claim extraction and critical-claim tagging (VER-1)
- [x] BM25 candidate retrieval over stored spans
- [x] Tier-1 deterministic verifier: number/date/unit match, hedge diff, fuzzy overlap (VER-2, VER-3)
- [x] Reports: per-turn markdown and JSON, summary line, `/qlaudified report`, `csv` (REP-2 to REP-4); `report --deep` moved to Sprint 3 with the LLM tier
- [x] Inline markers, using whichever approach Sprint 0 confirmed (REP-1)
- [x] Seed corpus: 5 Fernwick tasks with ground-truth TOML, used as integration-test fixtures
- [ ] Start dogfooding Medium on your own work: at the sprint's end, set up a stable copy (testing.md)

**Done when:** on a seed task where a source says "estimated", qlaudified flags the dropped qualifier in the report, and Medium's measured overhead is under 10%.

## Sprint 3 · Web sources and model tiers (Oct 26–Nov 1)

Goal: cover web sources and add the two smarter verifier tiers, both optional and both logged.

- [x] WebFetch shadow re-fetch in the background, main-text extraction, raw/summary span linking (CAP-3)
- [x] Fallback to `summarized-only` on paywalls, JS-only pages and timeouts (CAP-4); hash mismatch handling
- [x] WebSearch results stored as `search-snippet` (CAP-5)
- [x] Local web server for saved Fernwick pages, so web tests are reproducible
- [x] Tier 2: NLI as the `[nli]` extra, ONNX Runtime on CPU, borderline thresholds
- [x] Tier 3: one batched call with a JSON schema; `claude-cli`, `ollama` and `none` backends (CFG-1); `/qlaudified report --deep` (REP-2, moved from Sprint 2)
- [x] Recursion guard for nested `claude -p` (SID-3); `usage.jsonl` cost logging

**Done when:** a WebFetch on a seed page records both the raw text and the summary, a qualifier dropped by WebFetch itself is flagged, and each tier's decisions are labelled in the report.

## Sprint 4 · High mode and eval harness (Nov 2–8)

Goal: finish High mode and get the evaluation ready to run, so Sprint 5 is only running and writing.

- [x] In-loop sidecar on flagged sentences only (SID-1, SID-2)
- [x] Stop retry, capped at once per turn, with a factual issue list (VER-4)
- [x] Code-claim levels, minimal: behavior vs value claims on code sources; Medium checks behavior, High both (README drift is out of v1)
- [x] Expand the corpus to about 20 tasks, four of each task type, with ground-truth TOML (local docs and code only)
- [x] Eval runner: tasks × 3 live conditions (Off runs in Low) × 2 repeats, post-hoc scored offline, via `claude -p --output-format json`, resumable after interruptions
- [x] Scoring: qualifier preservation, attribution precision and recall, verifier accuracy, cost, latency
- [x] Dry run of 5 tasks under all conditions (haiku) to shake out the harness

**Done when:** a High-mode run forces one retry that fixes a dropped qualifier, and the dry run produces a scored results table.

## Sprint 5 · The Provenance Administrator (Nov 9–15)

Goal: rebuild the core around design revision 2. The sidecar records REQ-3.2 provenance rows for critical facts in a rolling, read-only `provenance.csv`; refeeding it is a mode switch. Revision 1's rules, re-fetch, markers, retry and eval harness carry over.

Already done in this sprint, before the redesign (still used):
- [x] Study framework: pressure prompt variants, runner variants and limit handling, paired comparisons with bootstrap intervals (docs/findings/sprint-5.md)

The rebuild:
- [x] Facts, not passages: rule extraction of fact rows (number, date, qualifier); a sources log with hashes; drop passage storage and the raw cache (PROV-1, NFR-8)
- [x] Interception: capture the user prompt and provided files (`UserPromptSubmit`); read Claude's reasoning since the last step from the transcript; detect uses of tracked facts in reasoning and tool inputs (INT-1 to INT-3)
- [x] Provenance Administrator: threshold-gated synchronous sidecar call per step; origin classification, hybrid resolution, qualifiers at the source and at first use, operational impact; small inputs and a stable prompt prefix (PROV-2 to PROV-6)
- [x] Rolling read-only `provenance.csv`, rewritten under the database lock after each update; `claims.csv` for verdicts (PROV-7, REP-3)
- [x] Refeed as a mode switch: session-start fact line, deltas with the CSV path on overflow, compaction digest, consult log (RFD-1 to RFD-4)
- [x] Modes per revision 2: Low = record, Medium = record + refeed, High = + retry (MOD)
- [x] Verification on facts plus source re-reads; the Administrator writes the report in one call at Stop (VER-1 to VER-4, REP-2)
- [x] Decay tasks: hedged fact at step 1, question 0, ~5 and ~15 steps later, plus a `/compact` variant, with ground truth for REQ-3.2 fields where unambiguous
- [x] Scorer: decay curve (qualifier at first use, later uses, final), ledger accuracy, consults, cost per row; protocol amendment before any study run
- [x] Tests and benchmarks: rule path p95 ≤ 400 ms (NFR-3, revised from 300 ms); sidecar step p95 ≤ 10 s; cost per qualifying step measured with a fake backend and one live call (docs/findings/sprint-5.md, Benchmarks)

**Done when:** a live task fills `provenance.csv` with REQ-3.2 rows step by step (record only in Low), Medium refeeds them, the report is written at Stop, and the decay tasks run end to end in a small dry run.

## Sprint 6 · Study and release (Nov 16–22)

Goal: run the study, publish the numbers honestly, and ship v1.

- [ ] Pilot (haiku): cost per row and per run for each mode; set NFR-1 and NFR-2; go/no-go on the decay tasks' drop rate — run Oct 9: go (Low drops 86% under pressure); NFR-1/2 move to Sonnet repeat 1, where the agent's cost isn't dwarfed by the sidecar (docs/findings/sprint-6.md)
- [ ] Study runs on Sonnet and a haiku cross-check within the ~$25 budget, spread across days (plan usage plus extra credits)
- [ ] Results: decay curves and the Medium-vs-Low comparison as the headline; ledger accuracy; cost; consult rate
- [ ] Revisit NFR targets against measured numbers; record misses rather than hiding them
- [ ] README: what it does, install on Windows and macOS, quick start, modes, results, limitations
- [ ] 2–3 real-task demos with terminal screenshots or a short recording
- [ ] Tag v1.0.0 on GitHub with release notes

**Done when:** v1.0.0 is tagged and the README shows the measured results.

**If time runs short,** cut in this order: Ollama backend, NLI extra, the haiku cross-check. Never cut the Medium-vs-Low comparison on the decay tasks.

## Working rhythm

Solo sprints need only a light ritual: plan Monday, demo Sunday, and carry misses forward on purpose.

- **Monday:** pick the sprint's tasks into GitHub Issues, tagged with requirement IDs; move anything unfinished from last week explicitly.
- **During the week:** one branch per task, small PRs to yourself, CI green on both OSes before merge.
- **Sunday:** run the sprint demo against the "Done when" line, write three lines in `CHANGELOG.md`, update the design doc if a decision changed.
- **Buffer:** schoolwork and shifts will eat some weeks; the cut list in Sprint 5 is the pressure valve, not the release date.
