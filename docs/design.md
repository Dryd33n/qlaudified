# qlaudified — Design & Requirements

Oct 8, 2026 · Dryden

> Exported from the living design doc. Sibling files: `sprint-plan.md`, `testing.md`. Diagrams are described in text where they appeared.

## Overview

qlaudified is an open-source Claude Code plugin that tracks where each claim in Claude's answer came from, and whether the source's qualifiers ("estimated", "may", "tentative") survived the trip. It is built for daily use, documented as a portfolio piece, and backed by a measured evaluation.

**Problem.** Agents read sources across many steps, then answer in confident prose. Hedges get dropped, numbers drift, and citations point at pages that don't support the claim. Research on LM rewriting finds certainty is not preserved in up to 75% of outputs, and models amplify certainty more often than they soften it.

**Goals for v1**

- Record verbatim source spans for every retrieval from local docs, web pages and code, outside the context window.
- Feed compact provenance back to Claude during the run so qualifiers survive into the answer and across compaction.
- Verify each final claim against stored spans and show the result inline, as a full report, and as raw CSV.
- Keep overhead low: deterministic work first, models only when needed, no second API key required.
- Show measured results: qualifier preservation, attribution accuracy, cost and latency per mode.

**Non-goals for v1**

- A GUI or Agent SDK app (CLI plugin only).
- Training or fine-tuning any model.
- Attributing claims to training data. Anything not matched to a source span is reported as unsupported, not traced to pretraining.
- Enterprise features: auth, encryption at rest, multi-user audit.

## Decisions so far

These were settled in the kickoff Q&A; anything not listed here is still open (see the last section).

| Area | Decision |
| --- | --- |
| Purpose | Open-source plugin and portfolio project, with a real evaluation (not a research paper) |
| Form | Claude Code plugin, CLI only for v1 |
| Sources | Local doc folders, web pages, codebases |
| Language | Python for hooks, verifier and eval tooling |
| Verifier | Deterministic matching always; optional local NLI (`pip install qlaudified[nli]`); one batched LLM call for leftovers (automatic in High, on request in Medium) |
| Sidecar LLM | Reuse the Claude Code login via `claude -p` with a small model by default; configurable backend (e.g. Ollama) |
| Runtime behavior | Medium and High re-inject provenance; High adds a one-time Stop retry and the in-loop LLM sidecar |
| Web sources | Shadow re-fetch in v1 (Claude keeps using WebFetch); a raw-fetch MCP tool as a later High-mode opt-in |
| Code claims | Medium: behavior claims. High: behavior, README/doc facts, numbers and config values |
| Output | Inline answer markers, `/qlaudified report`, and an option to open `provenance.csv` |
| Storage | `.claude/.qlaudified/` inside the project |
| Platforms | Windows and macOS first |
| Evaluation | Synthetic planted-qualifier corpus plus a mode ablation |
| Distribution | GitHub repo only (clone + `--plugin-dir`) |
| Timeline | Solo, focused push of about a month |

## Provenance modes

The mode is the one knob users turn: each step up buys more checking for more time and usage. Every hook reads the mode first and exits immediately when it has nothing to do.

| Behavior | Low | Medium | High |
| --- | --- | --- | --- |
| Span capture on retrieval | Deterministic, silent | Deterministic (spans, numbers, dates, hedges) | Deterministic |
| In-loop LLM sidecar | Off | Off | On, filtered spans only |
| Re-inject provenance deltas | No | Yes | Yes |
| Web shadow re-fetch | No | Yes | Yes |
| Code claims tracked | None | Behavior claims | Behavior, doc facts, numbers and config |
| Final verification | None | Deterministic + NLI (if installed); LLM only via `report --deep` | Same, lower threshold for what counts as critical |
| Stop retry on dropped qualifier or unsupported claim | No | No | Once per turn |
| Inline markers and report | Report on request | Yes | Yes |
| Target overhead (cost-weighted) | ~0% | ≤ 10% | ≤ 20% |

Low captures spans silently at zero token cost, so `/qlaudified report` still works afterwards; nothing is injected or verified unless you ask.

## Functional requirements

Requirements are grouped by component and numbered so issues and tests can reference them.

**Mode control (MOD)**

- MOD-1: `/qlaudified mode <low|medium|high>` sets the mode for the project; `/qlaudified mode` with no argument prints the current mode.
- MOD-2: The mode persists in `.claude/.qlaudified/config.toml` and survives restarts.
- MOD-3: A one-session override is possible without changing the saved default.

**Capture (CAP)**

- CAP-1: After every retrieval tool call (`Read`, `Grep`, `WebFetch`, `WebSearch`, configured MCP tools, and Bash output per the decisions table), store each returned passage with source ID, location (path + line range, or URL + paragraph), timestamp and a content hash.
- CAP-2: Tag each stored span with detected numbers, dates, units, named entities and hedge words.
- CAP-3: For `WebFetch`, download the same URL separately, extract the main text, and store it as the raw source; store the WebFetch summary as a derived span linked to it.
- CAP-4: When the raw re-fetch fails (paywall, JS-only page, timeout), mark the source `summarized-only` rather than failing the hook.
- CAP-5: Store `WebSearch` results as `search-snippet` origin, weaker than a fetched page.
- CAP-6: Spans from subagents carry the subagent ID so multi-agent runs stay traceable.

**Re-injection (INJ)**

- INJ-1: In Medium and High, return only the provenance rows that are new since the last injection, as compact factual lines.
- INJ-2: Never exceed a configurable per-call budget (default 600 characters); summarize overflow as a count plus file path.
- INJ-3: After compaction, re-inject a compact digest of critical spans and qualifiers via `SessionStart` (`compact`).

**Sidecar (SID, High only)**

- SID-1: Send only flagged sentences (numbers, dates, hedges, entities), not whole documents, to the sidecar model.
- SID-2: The sidecar classifies each flagged span's criticality and extracts qualifiers it would miss lexically.
- SID-3: Nested `claude -p` calls run in safe mode (`--safe-mode`: no hooks, plugins or CLAUDE.md) to prevent recursion.

**Verification (VER)**

- VER-1: At `Stop`, split the final answer into atomic claims and link each to candidate spans.
- VER-2: Label each claim: supported, partially supported, qualifier dropped, contradicted, unsupported, or inference.
- VER-3: Run tiers in order (deterministic, then NLI if installed, then one batched LLM call) and record which tier decided.
- VER-4: In High, if any critical claim is contradicted or drops a qualifier, block the stop once with a factual list of the problems; never block twice in one turn.

**Reporting (REP)**

- REP-1: Rewrite the displayed answer with inline markers such as `[S3]`, `[S3, qualifier: estimated]` or `[unsupported]`; the stored transcript is unchanged.
- REP-2: `/qlaudified report` prints a claim-by-claim report for the last turn, with a summary line on top; adding `--deep` runs the LLM tier for that turn.
- REP-3: `/qlaudified csv` opens `provenance.csv` in the default app; `--path` prints its location.
- REP-4: Each turn's report is also saved as markdown and JSON under the session folder.

**Configuration (CFG)**

- CFG-1: The LLM backend is configurable: `claude-cli` (default, model configurable), `ollama`, or `none`.
- CFG-2: Hedge lexicon, critical-claim threshold and injection budget are configurable per project.

## Non-functional requirements and token budget

Overhead is measured cost-weighted (dollars or plan usage), not in raw tokens, because a sidecar token on a small model costs several times less than one on the primary model.

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-1 | Cost overhead, Medium | ≤ 10% over the plugin-off baseline, averaged across the eval set |
| NFR-2 | Cost overhead, High | ≤ 20% over baseline |
| NFR-3 | Capture hook latency, Medium | p95 ≤ 300 ms per retrieval, excluding network re-fetch |
| NFR-4 | Web re-fetch | Runs in the background; never blocks the agent loop for more than 2 s |
| NFR-5 | Stop verification time | p95 ≤ 5 s for Medium on a typical answer (≤ 20 claims) |
| NFR-6 | Install | `pip install qlaudified` works on Windows and macOS with no compiler; NLI is an optional extra |
| NFR-7 | Failure safety | Any hook error is logged and the run continues unchanged; qlaudified never breaks a session |
| NFR-8 | Privacy | All provenance data stays local; nothing leaves the machine except calls to the configured LLM backend |

**How the budget is kept**

1. **Deltas, not the whole CSV.** Earlier injections stay in the conversation and are prompt-cached, so each hook adds only new rows, about 30–60 tokens each.
2. **Deterministic first.** Span indexing, number and date matching and hedge diffs cost no model tokens.
3. **Filter before any model.** The High sidecar sees flagged sentences only, typically a small fraction of each document.
4. **Batch the LLM.** Verification makes at most one LLM call per turn, covering every unresolved claim.
5. **Measure it.** The sidecar logs its own usage, since calls made from hooks are not counted in Claude Code's cost output.

## Architecture

qlaudified is a plugin folder: four hooks, one command and a Python package. Claude Code is never patched; the hooks observe events and add context.

*Diagram — "Four hooks connect Claude Code to a local Python core" (three layers, top to bottom):*

- **Claude Code session:** Claude (primary agent, unchanged) · Retrieval tools (Read, Grep, WebFetch, WebSearch, MCP, Bash) · `/qlaudified` command (mode, report, open CSV).
- ↓ *tool results, final answer* / ↑ *deltas, digest, one retry*
- **Hooks (plugin):** Capture (`PostToolUse`: spans + deltas) · Digest (`SessionStart` `compact`: after compaction) · Verify (`Stop`: claims to verdicts) · Markers (`MessageDisplay`: inline `[S3]` tags).
- ↓ *calls*
- **qlaudified core (Python):** Span indexer (numbers, dates, hedge words) · Web re-fetch (raw page vs WebFetch summary) · Sidecar (High mode only, flagged spans) · Verifier (rules, then NLI, then one LLM call).
- ↓ *read and write* → **Session store** (`.claude/.qlaudified/`: SQLite, CSV, reports)
- ↓ *unresolved claims* → **LLM backend** (`claude -p` small model, or Ollama, or none)

Hooks stay thin and call into the core, so the same logic can later back an Agent SDK GUI.

```
qlaudified/
  .claude-plugin/plugin.json
  hooks/hooks.json          PostToolUse, SessionStart, Stop, MessageDisplay
  commands/qlaudified.md    /qlaudified mode | report | csv
  qlaudified/               Python package
    capture.py  refetch.py  sidecar.py  verify/  store.py  backends/
  eval/                     corpus, tasks, runner
```

## Flows

Every retrieval adds a few compact rows to Claude's context; at the end, verification either saves the report or, in High only, sends Claude back once.

*Diagram — "Provenance flows back into the loop after every retrieval":*

1. User prompt → Claude reasons → Retrieval tool call → Capture hook → **Inject new rows** (new rows only) → back to Claude reasons. Side notes: WebFetch triggers a raw re-fetch in the background; in High, the sidecar runs on flagged spans.
2. When Claude stops calling tools: final answer → Markers on display → `Stop`: verify claims.
3. Decision "Problem in High?": **yes** → Block, list issues → Claude revises once (back to Claude reasons). **No, or already retried** → Save report.

Compaction is the other flow: when Claude Code compacts the conversation, the `SessionStart` hook (`compact`) re-injects a digest of the critical spans and their qualifiers, which the transcript summary would otherwise lose. Web shadow re-fetch runs in the background and attaches the raw page to the span when it finishes.

## Data model

Everything lives under `.claude/.qlaudified/` in the project, one folder per session, with a SQLite index for fast lookup and `provenance.csv` as the human-readable export.

```
.claude/.qlaudified/
  config.toml            mode, backend, budgets, lexicon overrides
  .gitignore             ignores everything below by default
  sessions/<session_id>/
    index.sqlite         spans, claims, links (source of truth)
    provenance.csv       flat export of spans + claim verdicts
    raw/<hash>.txt       verbatim source text (re-fetched pages, file snapshots)
    reports/turn-<n>.md  human report per turn
    reports/turn-<n>.json
    usage.jsonl          sidecar and verifier token/cost log
```

**Span record** (one per captured passage)

| Field | Example | Notes |
| --- | --- | --- |
| `span_id` | `S14` | Short ID used in markers and injections |
| `origin` | `local-doc` | `local-doc`, `code`, `command-output`, `web-raw`, `web-summary`, `search-snippet`, `user-prompt` |
| `source` | `notes/q3.md` or a URL | |
| `locator` | `L22-L24` or `p7` | Line range, or paragraph index for web |
| `text` | verbatim passage | Capped length; full text in `raw/` |
| `numbers` | `4.2M USD; 2026-09-30` | Normalized values |
| `qualifiers` | `estimated; preliminary` | From lexicon, plus sidecar in High |
| `derived_from` | `S13` | Links a WebFetch summary span to its raw page span |
| `agent_id` | `main` | Subagent ID when captured inside one |
| `turn`, `ts`, `hash` | | Ordering and change detection |

**Claim record** (one per atomic claim in a final answer): `claim_id`, `turn`, `text`, `span_ids`, `verdict`, `dropped_qualifiers`, `decided_by` (`deterministic`, `nli` or `llm`), `confidence`, `critical`.

**Injection line format** (what Claude sees mid-run): `[S14 notes/q3.md L22] Q3 revenue 4.2M USD; source says: estimated, preliminary`. Plain facts, no instructions, so it doesn't trip prompt-injection defenses.

## Verification pipeline

Each claim goes through the cheapest tier that can decide it, and only unresolved claims move on, so most turns never call a model.

1. **Claim extraction.** Split the answer into sentences, then into atomic claims at conjunctions and lists (rule-based). Mark a claim critical if it carries a number, date, named entity, comparison or qualifier. In Medium, non-critical claims are skipped.
2. **Candidate retrieval.** For each claim, pull the top 3–5 spans by BM25 over stored span text, boosted by shared numbers and entities. No embeddings in v1, to keep installs light.
3. **Tier 1, deterministic.** Normalize and compare numbers, dates and units ("$4.2M" = "4.2 million USD"). Diff hedge words between span and claim. Measure fuzzy token overlap. Decides: exact support, number mismatch (contradicted), and dropped qualifier.
4. **Tier 2, NLI (optional extra).** A small DeBERTa-class MNLI model, run with ONNX Runtime on CPU, scores each (span, claim) pair as entails, neutral or contradicts. Confident results are final; borderline ones move on.
5. **Tier 3, LLM (one batched call).** All leftover claims plus their candidate spans go to the configured backend in a single prompt with a strict JSON output schema. Handles paraphrase, synthesis across sources and "is this inference reasonable?" Automatic in High; in Medium only via `/qlaudified report --deep`.
6. **Classify.** Claims with no span above threshold become `unsupported`; claims combining several spans become `inference` with all their span IDs listed.

**Hedge lexicon.** v1 ships a curated list grouped by strength (e.g. *may/might/could*, *estimated/approximately/preliminary*, *reportedly/allegedly*, *likely/unlikely*). A qualifier counts as dropped when the span's strongest hedge class is missing from the claim. The lexicon is user-extendable in `config.toml`.

**Backends.** `claude-cli` runs `claude -p --model <small model> --output-format json` in safe mode with a JSON schema; `ollama` calls the local HTTP API; `none` skips tier 3 and reports leftovers as `unresolved`.

## Evaluation plan

The headline question: does re-injecting provenance during a run preserve qualifiers better than checking only afterwards, and at what cost? Two pieces answer it: a synthetic corpus where every answer is known, and an ablation across four conditions.

**Synthetic corpus ("Fernwick Co.", a fictional company)**

- Local docs: about 30 markdown and PDF files (memos, meeting notes, reports) with planted facts, each with a known qualifier and source.
- Code: a small repo whose README and config state limits and values, some deliberately out of sync with the code.
- Web: saved HTML pages served from a local web server, so re-fetch is reproducible and the internet isn't needed.
- About 20 tasks, four of each of five types:

| Task type | What it tests | Example |
| --- | --- | --- |
| Single-hop hedged fact | Qualifier survives one read | "What was Q3 revenue?" (source says *estimated*) |
| Multi-hop chain | Qualifier survives 2–3 documents | Memo cites report, report hedges the figure |
| Conflicting sources | Correct attribution between near-duplicates | Two reports disagree on a date |
| Compaction stress | Provenance survives `/compact` | Long task with a forced compaction midway |
| No-source question | Unsupported claims flagged | Asks something no file contains |

Ground truth is a YAML file per task listing the expected facts, their source spans and qualifiers, so scoring is automatic.

**Ablation conditions**

1. Off (plugin disabled)
2. Post-hoc only (Stop verification, no re-injection)
3. Medium
4. High

Comparing 2 and 3 isolates the main contribution.

**Metrics**

- Qualifier preservation rate: planted hedges still present in the final answer.
- Attribution precision and recall: claim-to-span links against ground truth.
- Verifier accuracy: qlaudified's verdicts against the known answer.
- Cost overhead per condition: Claude Code's `total_cost_usd` plus the sidecar's `usage.jsonl`.
- Latency: hook and verification timings.

**Harness, sized for a Pro plan.** Only three conditions run live: Off, Medium and High. The post-hoc condition is the Off transcripts verified offline, which gives the same answers without new runs. 20 tasks × 3 live conditions × 2 repeats is about 120 short runs on a Sonnet-class primary model, spread over about a week with a daily cap from the cost ledger. If the cap bites, the second repeat of the Off condition goes first. Every run is recorded, so verifier changes are re-scored for free.

## Milestones

Six one-week sprints, starting with a three-day spike on Oct 9, lead to an evaluated v1.0.0 on Nov 15. Medium mode is usable daily by the end of Sprint 2.

*Timeline — "Six sprints to an evaluated v1 on Nov 15":* S0 Spike (Oct 9–11) · S1 Foundations + capture (Oct 12–18) · S2 Medium end to end (Oct 19–25) · S3 Web + model tiers (Oct 26–Nov 1) · S4 High + eval harness (Nov 2–8) · S5 Results + release (Nov 9–14) · v1.0.0 on GitHub (Nov 15).

Tasks, requirement IDs and the "done when" check for each sprint are in `sprint-plan.md`.

## Decisions to lock in now

These close gaps that would otherwise surface mid-sprint. All are settled as of Oct 8.

| Area | Decision | Why it eases development |
| --- | --- | --- |
| Runtime dependencies | Core is standard library only (`json`, `sqlite3`, `re`, `urllib`, `html.parser`); `[web]` and `[nli]` are pip extras | Hooks run on plain system Python with no virtualenv to locate, and start fast |
| Python | 3.10+; the Python command is configurable (`python` or `py -3`) | On Windows, `python` can be the Microsoft Store stub; Sprint 0 checks it |
| Hook entry point | One `run.py <event>` dispatcher with lazy imports | One place for error handling, logging and timing; keeps NFR-3 reachable |
| Turn identity | `session_id` names the session folder; `prompt_id` keys each turn | Both come from Claude Code, so there are no counters to keep in sync |
| Concurrency | SQLite in WAL mode with a busy timeout | Parallel tool calls fire several hooks at once |
| Store | SQLite is the source of truth; `provenance.csv` is an export | Fast lookups for the verifier, readable CSV for people |
| What counts as retrieval | `Read`, `Grep`, `WebFetch`, `WebSearch`, MCP tools, and all Bash output as `command-output` spans; simple file reads (`cat`, `type`, `Get-Content`, `head`, `tail`, `sed -n`) are upgraded to file spans with line ranges; huge or install-style output is skipped | Claims backed by scripts and tests stay sourced instead of showing as unsupported |
| `Read` output | Strip line-number prefixes; keep the numbers as the locator | Spans must hold the file's real text |
| Subagents | Capture inside subagents; their injections land in their own context; a subagent's reply becomes a span derived from its sources | Explore-style agents do much of the reading |
| Claim parsing | Claims come from prose, list items and table cells; code blocks are skipped | Code isn't a factual claim about a source |
| Web re-fetch | Runs as an `async` hook | Never blocks the loop, with no threading code of our own |
| Low mode | Capture only: no injection or verification; report on request | Costs zero tokens and still leaves a trail |
| Commands | One `/qlaudified` command: `mode`, `report`, `report --deep`, `csv` | One file to maintain, one name to learn |
| LLM tier in Medium | On request only: `/qlaudified report --deep` runs it for that turn; automatic in High | Medium stays free on a Pro plan; you pay only for answers you check |
| Retention | Prune sessions after 30 days; cap the raw cache at 200 MB; auto `.gitignore` | Raw copies can hold secrets and grow quickly |
| Compatibility | Pin a minimum Claude Code version; `SessionStart` warns when older | Hook fields change between versions |
| Eval primary model | Sonnet class | Closest to real use; the run count is capped by the cost ledger |
| Name | Keep qlaudified, defined in one place; check Anthropic's brand guidelines before publishing, since it echoes "Claude" | A later rename is one edit, not a search |

## Risks and open questions

The biggest technical risk is inline markers: the display hook runs while the answer streams, before Stop verification has a verdict.

**Risks**

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Markers need verdicts that don't exist yet while streaming | Inline markers show nothing useful | Markers from fast deterministic span matching during display; full verdicts in a summary line at Stop and in the report |
| `claude -p` startup takes seconds and uses plan limits | Slow Stop in High, eval runs throttled | One batched call per turn; keep it to tier 3 only; Ollama as a local fallback |
| Windows hook quirks (paths with backslashes, PowerShell vs Git Bash) | Hooks fail silently | Exec form with `python` + script path; normalize paths; CI on both OSes |
| Re-fetched page differs from what WebFetch saw | False "qualifier dropped" flags | Store a content hash; label mismatched pages `summarized-only` |
| Stored spans carry injected instructions | Re-injection relays an attack | Inject only extracted facts and qualifiers in a fixed format, never raw text |
| Rule-based claim splitting misses compound claims | Lower attribution recall | Measure it in the eval; let the tier-3 LLM split leftovers |
| Stop retry loops or annoys | Worse UX in High | Hard cap of one retry per turn; easy to disable |

**Open questions**

- [ ] Concrete criticality thresholds for Medium vs High: which claim types count, and at what confidence? (Sprint 2)
- [ ] Default small model for the `claude-cli` backend, chosen from Sprint 0 timings.
- [ ] Check the name against Anthropic's brand guidelines, and availability on GitHub and PyPI, before publishing.
- [ ] Which 2–3 real tasks to show as README demos once the eval is done.

Low mode, the command layout and the store format are now settled in the decisions table above.
