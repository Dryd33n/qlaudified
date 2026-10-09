# Sprint 3 notes (web sources and model tiers)

Kickoff note written at the end of Sprint 2 (Oct 8), so a fresh session can start here.

## Where things stand

Medium works end to end with rules only (docs/findings/sprint-2.md). The pipeline is in
`qlaudified/verify/__init__.py`: `claims_in_context` -> `candidates.Index.top` -> `tier1.check`
-> `classify.classify`. Claims no tier decides end up `unresolved` (some overlap) or `unsupported`.
Stubs waiting for this sprint: `verify/tier2_nli.py`, `verify/tier3_llm.py`, `refetch.py`,
`backends/claude_cli.py`, `backends/ollama.py`. `backends/fake.py` and `none.py` already work.
`cli.py` prints a "Sprint 3" note for `report --deep`.

## Suggested order (budget is tight: do one piece per session)

1. **Tier 3 + `report --deep`** (VER-3, REP-2, CFG-1). One batched `claude -p --safe-mode`
   call per turn for the `unresolved` and borderline claims, with a JSON schema; haiku by
   default (Sprint 0: ~1.7 s fixed + ~2.6 s per call). Medium runs it only on `report --deep`;
   High runs it at Stop. Test with `FakeBackend`; log usage to `usage.jsonl`. SID-3: the nested
   call must never load hooks or plugins.
2. **Web re-fetch** (CAP-3, CAP-4). An `async` PostToolUse hook downloads the same URL (stdlib
   `urllib` + `html.parser` main-text extraction), stores `web-raw` spans and sets the summary
   span's `derived_from`. Paywalls, JS-only pages and timeouts mark the source `summarized-only`.
   Tests use a local server for saved Fernwick pages. NFR-4: never block the loop for over 2 s.
3. **Ollama backend** (CFG-1), small.
4. **NLI tier** behind the `[nli]` extra (ONNX Runtime, CPU). Largest and riskiest; can slip
   past v1 if the budget runs out.

## Things learned in Sprint 2 to keep in mind

- In `claude -p`, the JSON `result` is the marked display text; strip markers before scoring.
- `live.py` steps (`---` in prompt.txt) need the transcript, so they keep prompt history on.
- Clauses take hedges from their whole sentence; Tier 1 compares spans sentence by sentence.
- WebSearch titles are stored but never injected.

## Results (Oct 8)

Built: tier 3 (one batched `claude -p --safe-mode` call with a JSON schema) with `claude-cli`,
`ollama` and `none` backends, `/qlaudified report --deep`, the LLM tier at Stop in High,
`usage.jsonl`, the NLI tier (`[nli]` extra, `/qlaudified nli install`), the WebFetch re-fetch
with `summarized-only` fallbacks, the summary-vs-page check, a local page server, and tier labels
in reports. 201 free tests pass; ruff and mypy are clean. Live spend: about $0.03.

| Check | Result |
| --- | --- |
| WebFetch on a real page (sqlite3 docs) | Summary span plus 200 `web-raw` spans; summary `derived_from = S2-S201`; no errors |
| Qualifier dropped by WebFetch itself | Flagged in tests (saved pricing page; the summary drops "expected to" and "subject to change"); the live summary kept its "may", so there was nothing to flag |
| Tier labels in the report | `(rules)`, `(NLI)` and `(LLM)` on each claim, all seen live |
| `report --deep`, live | 1 call, 2 claims, 3.4 s, $0.001 |
| High-mode Stop, live | LLM tier ran automatically: 4.0 s call, Stop 5.7 s in total |
| NLI tier | ~15–20 ms per pair; ~2.4 s to load, only when the rules leave a claim open |
| PostToolUse p95 (NFR-3) | 234 ms on Read, 267 ms on WebFetch (launching the re-fetch) |

Findings:
- **Async hooks are killed when a `claude -p` session ends** (hooks docs), so the re-fetch is a
  detached process started by the normal PostToolUse hook; Stop waits up to 8 s for it.
- **WebFetch upgrades `http://` to HTTPS**, so it can't fetch a local server. The saved pages
  serve the offline tests; live web tests use public pages. (In seed-web, Claude fell back to curl.)
- **Hooks run with `-S`**, so the NLI tier adds site-packages itself, and only once the model exists.
- **Replays and benchmarks run offline** (`QLAUDIFIED_OFFLINE=1`): no re-fetch and no LLM backend.
  The first deep test showed a replayed WebFetch fetching the live page.
- **NLI read a search title as a contradiction.** It now skips search snippets, and a
  contradiction needs at least 30% word overlap. Paraphrases may share no words.
- NLI treats a dropped "may" as neutral, not entailed, so qualifier checks stay with the rules
  and the LLM.
- The LLM labels claims about absence ("the file doesn't contain Q4 revenue") as unsupported,
  since no passage states an absence.
- The page cap is 200 paragraphs; longer pages are cut off (the sqlite3 docs hit it).

Recordings added: `seed-web`, `web-refetch` and `seed-high` (`tests/sessions/*-windows`).
