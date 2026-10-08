# Sprint plan

Six one-week sprints take qlaudified from a hook spike to a tagged, evaluated v1 on Nov 15, 2026.

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
| 5 | Nov 9–15 | Ablation results, README, v1 tag | Results table and charts in the README |

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

- [ ] WebFetch shadow re-fetch in the background, main-text extraction, raw/summary span linking (CAP-3)
- [ ] Fallback to `summarized-only` on paywalls, JS-only pages and timeouts (CAP-4); hash mismatch handling
- [ ] WebSearch results stored as `search-snippet` (CAP-5)
- [ ] Local web server for saved Fernwick pages, so web tests are reproducible
- [ ] Tier 2: NLI as the `[nli]` extra, ONNX Runtime on CPU, borderline thresholds
- [ ] Tier 3: one batched call with a JSON schema; `claude-cli`, `ollama` and `none` backends (CFG-1); `/qlaudified report --deep` (REP-2, moved from Sprint 2)
- [ ] Recursion guard for nested `claude -p` (SID-3); `usage.jsonl` cost logging

**Done when:** a WebFetch on a seed page records both the raw text and the summary, a qualifier dropped by WebFetch itself is flagged, and each tier's decisions are labelled in the report.

## Sprint 4 · High mode and eval harness (Nov 2–8)

Goal: finish High mode and get the evaluation ready to run, so Sprint 5 is only running and writing.

- [ ] In-loop sidecar on flagged sentences only (SID-1, SID-2)
- [ ] Stop retry, capped at once per turn, with a factual issue list (VER-4)
- [ ] Code-claim levels: behavior claims in Medium; doc facts, numbers and config values in High
- [ ] Expand the corpus to about 20 tasks, four of each task type, with ground-truth TOML
- [ ] Eval runner: tasks × 3 live conditions × 2 repeats, post-hoc scored offline, via `claude -p --output-format json`, resumable after interruptions
- [ ] Scoring: qualifier preservation, attribution precision and recall, verifier accuracy, cost, latency
- [ ] Dry run of 5 tasks under all conditions to shake out the harness

**Done when:** a High-mode run forces one retry that fixes a dropped qualifier, and the dry run produces a scored results table.

## Sprint 5 · Results and release (Nov 9–15)

Goal: run the ablation, publish the numbers honestly, and ship v1.

- [ ] Full ablation runs, spread across the week to stay inside plan usage limits
- [ ] Results: comparison table and charts; post-hoc vs Medium called out as the headline
- [ ] Revisit NFR targets against measured numbers; record misses rather than hiding them
- [ ] README: what it does, install on Windows and macOS, quick start, modes, results, limitations
- [ ] 2–3 real-task demos with terminal screenshots or a short recording
- [ ] Tag v1.0.0 on GitHub with release notes

**Done when:** v1.0.0 is tagged on Nov 15 and the README shows the measured results.

**If time runs short,** cut in this order: High-mode code-claim extras, Ollama backend, NLI extra. Never cut the post-hoc vs Medium comparison.

## Working rhythm

Solo sprints need only a light ritual: plan Monday, demo Sunday, and carry misses forward on purpose.

- **Monday:** pick the sprint's tasks into GitHub Issues, tagged with requirement IDs; move anything unfinished from last week explicitly.
- **During the week:** one branch per task, small PRs to yourself, CI green on both OSes before merge.
- **Sunday:** run the sprint demo against the "Done when" line, write three lines in `CHANGELOG.md`, update the design doc if a decision changed.
- **Buffer:** schoolwork and shifts will eat some weeks; the cut list in Sprint 5 is the pressure valve, not the release date.
