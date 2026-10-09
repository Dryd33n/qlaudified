# qlaudified — Design & Requirements

Oct 8, 2026 · Dryden · Revision 2 (the Provenance Administrator design)

> Sibling files: `sprint-plan.md`, `testing.md`, `evaluation.md`. Revision 2 realigns the build with
> the original idea: a sidecar agent records the provenance of critical facts as the agent works,
> and feeding that record back into the loop is the hypothesis under test. What changed from
> revision 1 and why is at the end ("Design history").

## Overview

qlaudified is an open-source Claude Code plugin for advanced research work. As Claude works, a
sidecar agent, the **Provenance Administrator**, records where each critical fact came from, how
it was qualified at the source, and how Claude used it, step by step, in a rolling read-only
`provenance.csv`. At the end it writes a provenance report for the answer. Optionally, the record
is fed back into Claude's loop so qualifiers survive many steps of work.

**Problem.** Agents read sources across many steps, then answer in confident prose. Hedges get
dropped, numbers drift, and citations point at sources that don't support the claim. Research on
LM rewriting finds certainty is not preserved in up to 75% of outputs, and models amplify
certainty more often than they soften it. The longer the task, the more steps a qualifier has to
survive.

**Who it's for.** Research-grade work where being right about what a source said matters more
than speed. Time is a secondary cost; token cost is the one to keep small.

**Goals for v1**

- Record a provenance row for every critical fact Claude encounters or states (REQ-3.2 fields:
  claim, origin, primary source for hybrids, qualifiers at the source and at first use, and
  operational impact), in a rolling, read-only `provenance.csv`.
- Feed the record back into the loop (Medium and High) and measure whether it keeps qualifiers
  alive across many steps.
- Produce a provenance report for each answer, cross-checked by exact rules for numbers, dates
  and qualifiers.
- Keep token cost low: rules first, the sidecar only on critical material, small inputs, small
  model.
- Show measured results: qualifier decay across steps, ledger accuracy, cost per mode.

**Non-goals for v1**

- A GUI or Agent SDK app (CLI plugin only).
- Training or fine-tuning any model.
- Proving that a claim came from training data. "Training Data" is a classification by
  elimination: a critical claim Claude states that no source in the session supports, judged by
  the sidecar as general knowledge rather than inference.
- Enterprise features: auth, encryption at rest, multi-user audit.

## Decisions so far

| Area | Decision |
| --- | --- |
| Purpose | Open-source research tool and portfolio project, with a measured evaluation |
| Core | The Provenance Administrator sidecar records REQ-3.2 provenance rows for critical facts |
| Hypothesis | Feeding the record back into the loop preserves qualifiers across steps (Medium vs Low) |
| Form | Claude Code plugin, CLI only for v1 |
| Sources | Local docs and code, provided documents, user prompts, web pages, command output, MCP tools |
| Language | Python for hooks, sidecar, verifier and eval tooling |
| Sidecar LLM | Reuse the Claude Code login via `claude -p --safe-mode` with haiku by default; Ollama as a local, zero-API-cost option |
| Timing | The sidecar runs synchronously: each row is complete before Claude's next step. Time is acceptable; token cost is minimized |
| Storage | Facts only, never passages: fact rows plus a log of sources read (path, lines, hash) |
| Output | Rolling `provenance.csv`, inline markers, provenance report, `/qlaudified report` |
| Storage location | `.claude/.qlaudified/` inside the project |
| Platforms | Windows and macOS first |
| Evaluation | Synthetic planted-qualifier corpus, decay tasks across step distances, mode ablation |
| Distribution | GitHub repo only (clone + `--plugin-dir`) |

## Provenance modes

| Behavior | Low | Medium | High |
| --- | --- | --- | --- |
| Rule-based fact extraction from every retrieval | Yes | Yes | Yes |
| Provenance Administrator sidecar (REQ-3.2 rows) | Yes | Yes | Yes |
| Rolling read-only `provenance.csv` | Yes | Yes | Yes |
| **Refeed**: new rows and the CSV's location go back into the loop | No | Yes | Yes |
| Compaction digest | No | Yes | Yes |
| Inline markers | No | Yes | Yes |
| Provenance report and summary line at the end | Yes | Yes | Yes |
| Stop retry when the answer drops a qualifier or contradicts a source | No | No | Once per turn |

Low records without influencing Claude: nothing reaches Claude's context, so Low is also the
eval's **record-only** condition. Medium is record + refeed, the hypothesis. High adds one retry.

## Functional requirements

**Mode control (MOD)** (unchanged)

- MOD-1: `/qlaudified mode <low|medium|high>` sets the mode for the project; no argument prints it.
- MOD-2: The mode persists in `.claude/.qlaudified/config.toml`.
- MOD-3: A one-session override is possible without changing the saved default.

**Interception (INT)**: what the sidecar sees

- INT-1: Capture the user's prompt at submission (`UserPromptSubmit`), and the files the prompt
  names or attaches, as origins in their own right.
- INT-2: After every tool call, collect the tool input, the tool output, and Claude's reasoning
  text since the previous step (from the session transcript).
- INT-3: Rules extract candidate facts (sentences or lines with a number, date or qualifier) and
  detect uses of known facts (their values appearing in Claude's text or tool inputs) before any
  model call.
- INT-4: Subagent calls carry their agent ID; their rows stay attributable (CAP-6 from rev 1).

**Provenance record (PROV)**: the Provenance Administrator, REQ-3.2

- PROV-1 **Critical claim description:** the statement, figure, date or condition identified as
  critical, one row per fact.
- PROV-2 **Origin classification:** Direct Retrieved Fact, Provided Document, Internal Document,
  User Prompt, Model Inference, Training Data, or Hybrid.
- PROV-3 **Primary source resolution (hybrids only):** which origin primarily influenced the claim,
  and whether the sources agreed.
- PROV-4 **Linguistic qualifiers:** the qualifiers in the original source, and those present at
  the claim's first use in Claude's reasoning or tool calls.
- PROV-5 **Operational impact:** how the claim was used in later tool calls and its effect on the
  final conclusion; updated as uses accrue, finalized at Stop.
- PROV-6 **Threshold:** the sidecar runs only when the step meets the mode's criticality threshold
  (rules found a new candidate fact or a use of a tracked fact). Steps with nothing critical cost
  no tokens.
- PROV-7 **Rolling and read-only:** `provenance.csv` is rewritten from the store after every
  update; its read-only attribute makes Claude's Write and Edit fail, and any change is undone at
  the next rewrite.

**Refeed (RFD)**: Medium and High

- RFD-1: At session start, tell Claude where the CSV is and what it holds, as a plain fact.
- RFD-2: After each step, return the new or changed rows as compact factual lines, within a
  per-call budget (default 600 characters); overflow is a count plus the CSV path.
- RFD-3: After compaction, re-send a digest of the qualified rows and the CSV's location.
- RFD-4: Log every time Claude reads the CSV (a consult), with its step and size.

**Verification and report (VER, REP)**

- VER-1: At Stop, split the final answer into claims and match each to fact rows.
- VER-2: Exact rule checks on numbers, dates, units and hedge classes label each claim:
  supported, qualifier dropped, contradicted, unsupported, or not checked.
- VER-3: Claims without a number, date or qualifier are checked by re-reading the sources Claude
  read (local files from disk, with a hash check; web pages via re-fetch). Command output and MCP
  results can't be re-read: those claims are reported as not checked.
- VER-4: In High, if a critical claim drops a qualifier or is contradicted, block the stop once with
  a factual list of the problems; never twice in one turn.
- REP-1: Inline markers such as `[F3]` or `[F3, qualifier: estimated]` on the displayed answer.
- REP-2: The Provenance Administrator writes the provenance report at Stop from the rows and the
  rule verdicts (one batched call); `/qlaudified report` prints it.
- REP-3: `/qlaudified csv` opens `provenance.csv` (and `claims.csv`); `--path` prints locations.
- REP-4: Each turn's report is saved as markdown and JSON.

**Configuration (CFG)**

- CFG-1: The sidecar backend is configurable: `claude-cli` (default, haiku), `ollama`, or `none`
  (rules only: the judgment fields stay empty).
- CFG-2: Hedge lexicon, criticality threshold and refeed budget are configurable per project.

## Non-functional requirements and token budget

Time is a secondary cost for research work; token cost is the one to shrink. Overhead is measured
cost-weighted (dollars or plan usage), because a haiku sidecar token costs several times less than
a primary-model token.

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-1 | Cost overhead, Medium (record + refeed) vs no plugin | Provisional ≤ 20%; set from the pilot |
| NFR-2 | Cost overhead, High vs no plugin | Provisional ≤ 30%; set from the pilot |
| NFR-3 | Rule path latency (no sidecar call) | PostToolUse p95 ≤ 400 ms (revised Oct 8 from 300 ms: revision 2 measures 360–390 ms; time is the accepted cost) |
| NFR-4 | Sidecar step latency | p95 ≤ 10 s per step that meets the threshold |
| NFR-5 | Stop and report time | p95 ≤ 30 s |
| NFR-6 | Install | `pip install qlaudified` works on Windows and macOS with no compiler |
| NFR-7 | Failure safety | Any hook or sidecar error is logged and the run continues unchanged |
| NFR-8 | Privacy | Provenance stays local; only the configured sidecar backend sees excerpts; no passages are stored |

**How the token budget is kept small**

1. **Rules first.** Fact extraction, value matching, use detection, qualifier checks and the
   verdicts cost no tokens. The sidecar fills only the judgment fields (origin, hybrid resolution,
   impact) and qualifiers the word list misses.
2. **Threshold.** Steps with no new candidate fact and no use of a tracked fact skip the sidecar.
3. **Small sidecar inputs.** The sidecar sees candidate sentences, Claude's latest reasoning
   (capped), the tool input, and only the ledger rows the step touches, never whole documents or
   the whole CSV.
4. **Stable prompt prefix.** Instructions and schema come first and never change, so repeated
   calls can reuse the prompt cache.
5. **Small model, or none.** Haiku by default; Ollama for zero API cost; `none` for rules only.
6. **Deltas, not the whole CSV.** Refeed sends only new or changed rows; Claude can read the full
   CSV when it wants to, and each read is logged so its cost is measured.
7. **One call at the end.** The report and any leftover judgments are one batched call per turn.
8. **Measure it.** Every sidecar call is logged to `usage.jsonl` (tokens, cost, time).

## Architecture

```
Claude Code session
  Claude (primary agent, unchanged) · tools · /qlaudified
      │ prompt, tool calls, results, reasoning (transcript)      ▲ refeed rows, digest, retry (Medium/High)
      ▼                                                          │
Hooks (plugin)
  UserPromptSubmit  PostToolUse  SessionStart  MessageDisplay  Stop
      │
      ▼
qlaudified core (Python)
  Rules: fact extraction, value/qualifier matching, use detection
  Provenance Administrator: sidecar calls (threshold-gated, synchronous)
  Ledger: SQLite (source of truth) → rolling provenance.csv (read-only)
  Verifier + report: rule checks, source re-reads, one report call
  Web re-fetch (background)
      │
      ▼
Session store .claude/.qlaudified/sessions/<id>/       Sidecar backend (claude -p haiku · Ollama · none)
```

```
qlaudified/
  .claude-plugin/plugin.json
  hooks/hooks.json          UserPromptSubmit, PostToolUse, SessionStart, MessageDisplay, Stop
  hooks/run.py, cli.py      entry points; launch.sh picks py -3 or python3
  skills/qlaudified/        /qlaudified mode | report | csv
  qlaudified/               Python package: capture, facts, administrator, ledger, refeed, verify, report
  eval/                     tasks, runner, scorer
```

## Flow of a task

1. **Query submission.** The user's prompt (and any attached or named files) is captured by
   `UserPromptSubmit`; facts in it become User Prompt or Provided Document rows.
2. **Context assembly.** Claude Code assembles the context. In Medium and High it includes the
   session-start fact line, earlier refeed lines and, after compaction, the digest.
3. **Primary loop and tool call.** Claude reasons and calls a tool.
4. **Data retrieval.** The tool runs and returns its result.
5. **Interception.** `PostToolUse` collects the tool input, the result and Claude's reasoning since
   the last step. Rules extract candidate facts and detect uses of tracked facts.
6. **Threshold and extraction.** If the step meets the mode's threshold, the Provenance
   Administrator fills the REQ-3.2 fields for new facts and updates rows whose facts were used.
7. **Record update.** Rows are written to SQLite and `provenance.csv` is rewritten (read-only).
8. **Refeed (Medium, High).** New and changed rows return to Claude as compact factual lines;
   the loop continues at step 3.
9. **Final synthesis.** When Claude answers, `MessageDisplay` adds markers (Medium, High);
   `Stop` checks the answer's claims against the rows, re-reads sources for claims without facts,
   finalizes operational impact, and the Administrator writes the report. In High, a dropped
   qualifier or contradiction blocks the stop once.
10. **Result.** The answer is shown with markers and a one-line summary; the report and CSV are
    available via `/qlaudified report` and `/qlaudified csv`.

## Data model

```
.claude/.qlaudified/
  config.toml              mode, backend, threshold, budgets, lexicon overrides
  .gitignore               ignores everything below
  sessions/<session_id>/
    index.sqlite           facts, uses, sources read, claims (source of truth)
    provenance.csv         rolling, read-only: one row per critical fact
    claims.csv             final-answer claims and verdicts
    sources.jsonl          sources read: path or URL, lines, content hash, step (no text)
    consults.jsonl         Claude's reads of provenance.csv
    reports/turn-<n>.md    provenance report per turn (and .json)
    usage.jsonl            sidecar token, cost and time log
```

**Fact row** (`provenance.csv`, column order as Claude sees it)

| Field | Example | Filled by |
| --- | --- | --- |
| `fact_id` | `F3` | rules |
| `claim` | Q3 revenue is estimated at $4.2M, based on preliminary figures | rules (PROV-1) |
| `value` | `4200000 USD` | rules |
| `origin` | `Internal Document` | rules for retrieval origins; sidecar for Inference, Training Data, Hybrid (PROV-2) |
| `source`, `locator` | `q3-update.md`, `L3` | rules |
| `source_qualifiers` | `estimated; preliminary` | rules + sidecar (PROV-4) |
| `first_use_step` | `5` | rules |
| `first_use_qualifiers` | `` (none: dropped at first use) | rules (PROV-4) |
| `uses` | `5:Write notes.md; 9:Bash calc.py` | rules |
| `primary_source`, `sources_agree` | `F3`, `yes` | sidecar (PROV-3, hybrids only) |
| `operational_impact` | Used to compute revenue per employee; drove the summary's headline figure | sidecar (PROV-5) |
| `agent_id`, `step`, `turn`, `ts` | `main`, `2`, … | rules |

**Injection line format** (refeed): `[F3 q3-update.md L3] Q3 revenue is estimated at $4.2M...;
source says: estimated, preliminary`. Plain facts, never instructions.

## Verification

The rule checks are the exact backbone under the sidecar's judgments.

1. **Claim extraction:** rule-based split into atomic claims; code blocks, headings and the
   assistant talking about itself are skipped.
2. **Matching:** claims with a number, date or qualifier match fact rows by value (0.5% tolerance,
   units, a less precise date matching a more precise one) and words.
3. **Rule verdicts:** a qualifier counts as dropped when the claim lacks the source fact's
   strongest hedge class (attribution > tentative > estimate > likelihood > modal); a different
   value on the same topic is a contradiction.
4. **Re-reads:** claims without facts are checked against the sources Claude read, re-read from
   disk (hash-checked) or re-fetched; command and MCP output can't be re-read.
5. **Report:** the Administrator writes the report from rows, uses and verdicts in one call.

## Evaluation plan

The headline question: **does feeding the provenance record back into the loop keep qualifiers
alive across steps, and at what token cost?** Details and the pre-registered protocol:
`evaluation.md` and `findings/sprint-5.md`.

- **Conditions:** Off (no plugin) · Low (record only) · Medium (record + refeed) · High (+ retry).
  The headline compares Medium with Low; Low with Off checks the record itself has no effect.
- **Tasks:** the 20-task Fernwick corpus (natural and pressure prompts) plus decay tasks where the
  question comes 0, ~5 or ~15 steps after the hedged fact is read.
- **Measures:** qualifiers kept in the final answer; the decay curve (qualifier present at first
  use, at later uses, at the end); ledger accuracy against ground truth (claims, origins,
  qualifiers); verifier accuracy; consults of the CSV; cost per condition and per row.

## Milestones

Sprints 0–4 built revision 1 (rule-based capture and verification, deltas, High mode, eval
harness). Sprint 5 rebuilds the core around the Provenance Administrator; Sprint 6 runs the study
and releases v1. Details in `sprint-plan.md`.

## Decisions to lock in

Technical decisions that carry over from revision 1, plus the new ones.

| Area | Decision | Why |
| --- | --- | --- |
| Runtime dependencies | Core is standard library only; `[nli]` is an optional extra | Hooks run on plain system Python with no virtualenv |
| Python | 3.11+; `run.py` explains older interpreters and exits 0 | Bare `python` on Windows can be the Store's 3.9 (Sprint 0) |
| Hook command | One shell-form line per hook: `py -3 -S` if present, else `python3 -S`; Git for Windows required | One hooks.json for both OSes (Sprint 1) |
| Hook entry point | One `run.py <event>` dispatcher with lazy imports | One place for error handling, logging and timing |
| Turn and step identity | `session_id` names the session folder, `prompt_id` keys each turn, steps count tool calls within the session | No counters to keep in sync across processes beyond the store |
| Concurrency | SQLite WAL with a busy timeout; the CSV is rewritten under the database lock | Parallel tool calls fire several hooks at once |
| Store | SQLite is the source of truth; `provenance.csv` is rewritten from it after every update and kept read-only | Any edit to the CSV is undone at the next rewrite |
| What is a fact | A sentence or line with a number, date or qualifier (lexicon, plus sidecar finds). Named entities alone don't make a fact | Keeps the ledger to tens of rows, not every sentence |
| Passages | Never stored. Sources read are logged with a hash; local files are re-read from disk when needed, web pages re-fetched; command and MCP output keep only their facts | Small store, little copied text (NFR-8) |
| Sidecar timing | Synchronous in every mode, gated by the threshold; the web re-fetch stays a background job | Rows are complete before Claude's next step; time is acceptable, tokens are minimized |
| Reasoning text | Read from the transcript (`transcript_path` in every payload): assistant text since the last tool result. Thinking arrives empty (redacted) in `claude -p`, so in practice this is Claude's visible text plus its tool inputs | Hooks don't receive Claude's reasoning directly |
| Use tracking | A use is a clause stating a tracked fact's value on the same topic (topic overlap ignores numbers and runs both ways); its qualifiers are the hedges in that clause. Figures Claude states that match no fact become its own claim rows (Model Inference, Training Data or Hybrid, for the sidecar). The final answer is the last use | Found in Sprint 5: a shared figure alone isn't a shared topic, and a hedge belongs to the figure in its own clause |
| Retrieval tools | `Read`, `Grep`, `WebFetch`, `WebSearch`, MCP tools, `Bash` and `PowerShell` output; simple file reads become file facts with line numbers | Mapped in Sprint 0 |
| Paths | Normalize 8.3 short names and separators, store relative to the project | Sprint 0 |
| Self-capture | Never capture the store; reads of `provenance.csv` are logged as consults instead | Sprint 0 |
| Subagents | Facts and uses carry the agent ID; refeed lands in that agent's context | Sprint 0, Sprint 1 |
| Web re-fetch | Background job from PostToolUse; Stop waits up to 8 s | `async` hooks die with `claude -p` (Sprint 3) |
| Stop retry | `{"decision": "block", "reason": <factual problem list>}`, never when `stop_hook_active`; counts as one `--max-turns` turn | Confirmed live (Sprint 4) |
| Recording | `QLAUDIFIED_RECORD_DIR` makes `run.py` log every event and response | Live runs become replay fixtures |
| Offline runs | `QLAUDIFIED_OFFLINE=1` turns off the re-fetch and real sidecar backends | Tests and replays never spend usage |
| Commands | One `/qlaudified` plugin skill: `mode`, `report`, `csv` | No model turn per command |
| Retention | Prune sessions after 30 days; auto `.gitignore` | Stores can hold excerpts of private sources |
| Compatibility | Claude Code 2.1.294+ | The versions tested |

## Risks and open questions

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Sidecar cost per step | Overhead too high for daily use | Threshold, small inputs, haiku or Ollama, rules for exact fields; measured per row in the pilot |
| Sidecar latency (3–5 s per qualifying step) | Slower runs | Accepted for research use; the threshold skips most steps |
| Reasoning text from the transcript | Format may change between versions; thinking may be redacted | Parse only assistant text blocks; fall back to tool inputs alone |
| Origin judgments (inference vs training data) are subjective | Ledger accuracy hard to score | Ground truth for origins only where the corpus makes it unambiguous; report agreement, not truth, elsewhere |
| Claude ignores the CSV | Refeed has no effect | The consult log measures it; deltas still carry the key facts |
| Claude's own notes become sources | A dropped qualifier gets laundered | Files Claude wrote in the session are derived, not sources (open item) |
| Injected rows read as instructions | Prompt-injection defenses trip | Plain facts in a fixed format, never raw source text |

**Open questions**

- [ ] Files Claude writes in the session: mark as derived, and flag hedged figures written without
  their hedge at write time?
- [ ] Separate `claims.csv`, or claim verdicts in the main CSV?
- [ ] Decay distances: 0, ~5, ~15 steps, or a longer tail?
- [ ] Final NFR-1 and NFR-2 targets, from the pilot's measured cost per row.

## Design history

**Revision 1 (Sprints 0–4)** made rule-based capture and verification the core: every passage
stored as a span, deltas injected in Medium, a small background sidecar in High only, and
verification at Stop by rules, optional NLI and an LLM tier. It met its latency targets and
showed the mechanisms work (findings for Sprints 0–4).

**Revision 2 (Oct 8)** returns to the original idea: the sidecar's provenance record is the
product, built per REQ-3.2, and refeeding it is the hypothesis. What changed and why:

- The sidecar moves from a High-only extra to the core of every mode, and runs synchronously.
- Facts replace passages in storage; non-fact claims are checked by re-reading sources.
- Rows follow a claim through the loop (first use, uses, impact), not just its source.
- `provenance.csv` becomes rolling and read-only, and Claude is told where it is.
- Low now records with the sidecar (no longer free) and is the eval's record-only condition.
- Rule verification, the web re-fetch, markers, the retry and the eval harness carry over.
- Superseded: per-passage spans and their BM25 index, Medium's code-claim level, NLI as a tier
  (kept as an optional extra for re-read claims), and the 300 ms target for every PostToolUse.
