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
