# Sprint 4 notes (High mode and eval harness)

Prep on Oct 8, 2026. Results are added at the sprint's end.

## Decisions (Oct 8)

- **Sidecar runs detached** (SID-1, SID-2). PostToolUse in High launches a background haiku call
  on the new spans' flagged sentences, as the re-fetch does, and returns at once. Its criticality
  and extra qualifiers are stored on the spans and reach Claude with the next tool call's delta;
  Stop always sees them (Stop already waits for pending background work).
- **Code-claim levels, minimal version.** Claims whose candidates are code spans are tagged as
  behavior claims (what code does) or value claims (numbers, config values, doc facts). Medium
  checks behavior claims only; High checks both. README-vs-code drift is out of scope for v1.
- **The eval's Off condition runs in Low mode.** Low adds nothing to Claude's context, so Claude
  sees exactly what it sees without the plugin, and the captured spans make the post-hoc
  condition an exact offline re-verification of the Off runs. A few `--no-plugin` runs check
  that the costs match.
- **Models:** the Sprint 4 dry run uses haiku (5 tasks × 3 conditions, about $0.05); Sprint 5's
  ablation uses Sonnet (about 20 tasks × 3 × 2, roughly $2–5 of plan usage over several days).
- **The corpus stays local** (docs and code). WebFetch upgrades `http://` to HTTPS, so it can't
  read saved pages from a local server (Sprint 3); web behavior stays covered by the offline tests.

## Stop retry facts (VER-4)

From the hooks docs and a live probe (`claude -p`, haiku, a throwaway plugin):

- `{"decision": "block", "reason": "..."}` keeps Claude going; the `reason` goes to Claude. Exit
  code 2 with stderr does the same.
- `stop_hook_active` is `true` on the Stop that follows our own block: never block then (VER-4's
  once-per-turn cap). Claude Code also overrides a hook after 8 consecutive blocks.
- **Probe:** the first Stop blocked with a factual problem list; Claude rewrote "The launch is
  planned for November 18, 2026." as "…, though that date is not yet confirmed." The second Stop
  had `stop_hook_active: true`, and the run ended normally with the new answer as `result`.
- **The retry counts as a turn:** the probe used both turns of `--max-turns 2`. High eval runs
  need one spare turn.
- Not documented, untested: whether a `systemMessage` beside `decision: "block"` is shown in an
  interactive session (it isn't visible in `-p`). Check in dogfooding.
- Lexicon gap seen in the probe: "not yet confirmed" isn't a tentative hedge yet.

## The reason text

The block reason is the only thing qlaudified ever tells Claude to act on, so it stays factual: a
numbered list of the problems (claim, verdict, dropped words, source span and its text), with no
imperative beyond what Claude Code's continuation already implies.

## Results (Oct 8)

Built: the Stop retry (VER-4), the background sidecar (SID-1, SID-2), code-claim levels, the
corpus at 20 tasks (4 per type), `eval/run.py` and `eval/score.py`, and a `mode` option for
`live.py` and the simulator. 245 free tests pass; ruff and mypy are clean. Live spend: $0.08.

**Demo: the retry fixes a dropped qualifier** (`retry-demo`, High, haiku, recorded as
`tests/sessions/retry-demo-windows` and replayed in High in CI):

1. Prompt: "reply with exactly one line ... no caveats: Q3 revenue was <amount>."
2. Claude: "Q3 revenue was $4.2M." Stop blocked once: `"Q3 revenue was $4.2M." drops the source's
   qualifier "estimated", "preliminary". [S2 q3-update.md L3] "Q3 revenue is estimated at $4.2M..."`
3. Claude: "Q3 revenue was an estimated $4.2M, based on preliminary figures from finance." The
   second Stop passed. $0.0024 in total.

**Dry run** (5 seed tasks × 3 conditions, haiku, one repeat; `eval/score.py`):

| Condition | Runs | Qualifiers kept | Drops flagged | Verifier accuracy | Attribution P / R | Cost per run | Overhead vs off | PostToolUse p95 | Stop p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| off | 5 | 100% (6/6) | n/a | n/a | n/a | $0.0035 | +0.0% | 196 ms | 127 ms |
| post-hoc | 5 | 100% (6/6) | – | 100% (7/7) | 100% (7/7) / 100% (7/7) | $0.0035 | 0% (offline) | 196 ms | 127 ms |
| medium | 5 | 83% (5/6) | 100% (1/1) | 100% (7/7) | 100% (7/7) / 100% (7/7) | $0.0039 | +8.0% | 166 ms | 1973 ms |
| high | 5 | 100% (6/6) | – | 100% (7/7) | 100% (7/7) / 100% (7/7) | $0.0046 | +37.9% | 209 ms | 8394 ms |

What it says, and what it doesn't:
- **The harness works end to end**: resumable runs, recordings, offline re-verification and a
  table. Five tasks and one repeat are far too few to compare conditions; that's Sprint 5.
- **Medium's one "drop" is a paraphrase**: "subject to change" became "it may change after the
  beta". Lexical scoring (and the verifier) count that as dropping the tentative class. Both
  should accept a weaker class only with care; revisit with Sprint 5 data.
- **High misses NFR-2 on haiku (+38% against ≤ 20%).** 9 sidecar calls and 2 LLM-tier calls cost
  $0.0044 over 5 runs (~$0.0009 per run). With haiku as the primary model, the sidecar is as
  expensive per token as Claude; on Sonnet (Sprint 5) the same calls are a much smaller share.
  If it still misses, the lever is fewer sidecar calls (only for spans with numbers, or one call
  per turn).
- **Medium's Stop p95 of ~2 s is the NLI tier loading**: the model is installed on this machine,
  and Stop loads it when the rules leave a claim open. Still under NFR-5's 5 s; machines without
  the model see ~130 ms. High's ~8 s is Stop waiting for the sidecar plus the LLM tier.

Found while building:
- **The sidecar once called "due on" a qualifier**, and the retry made Claude add "on". Its finds
  are still reported, but only lexicon hedges and contradictions can block.
- **"a May 2027 opening" read the month as the hedge "may"** (found by the new corpus); fixed.
- Code identifiers (`SYNC_INTERVAL_S`, `run()`) now count as named entities, so behavior claims
  about code are critical in Medium.
- Tests run offline by default (no background jobs, no real LLM backend), so no test can make a
  model call by accident; the WebFetch test opts out explicitly.
- Sandbox config files under `.claude/.qlaudified/` are git-ignored, so modes are set by
  `live.py --mode`, the eval runner and `replay(mode=...)`, never by files in `tests/sandbox`.
