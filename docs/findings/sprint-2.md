# Sprint 2 notes (Medium mode end to end)

Started with the prep on Oct 8, 2026. Results are added at the sprint's end.

## Prep decisions (Oct 8)

- **Ground truth is TOML**, read with `tomllib` (standard library), instead of YAML.
- **`/qlaudified report --deep` moves to Sprint 3**, along with the LLM tier it runs. Until then
  it prints a note saying so.
- **The dogfooding stable copy** is set up at the end of Sprint 2, once Medium mode is worth
  using day to day.

## MessageDisplay facts (hooks docs, Claude Code 2.1.295)

- Claude Code **holds each streamed batch until the hook returns**; if the hook fails or times out
  (10 s default), the original text is shown.
- Batches are newly completed whole lines; `final` marks the last one (its `delta` may be empty in
  interactive runs). `message_id` is stable within a message.
- In `claude -p` and the Agent SDK it runs **once per message with the full text** (`index` 0,
  `final` true). The eval runs see one call per message.
- `displayContent` replaces only what's shown; the transcript and Claude keep the original.

## Latency floor for markers

`scripts/bench_capture.py --event MessageDisplay --fixture message_display_partial` runs the
hooks.json command with a handler that does nothing: **p50 189 ms, p95 223 ms**. That's Git Bash,
the `py` launcher, the interpreter and `run.py`'s imports. Each streamed paragraph is held at least
this long, plus the marker matching.

- Sprint 2 target: keep the marker work itself under ~50 ms (read spans, match numbers and
  phrases; no BM25 rebuild per batch), for roughly 250–300 ms per paragraph.
- If that feels sluggish in dogfooding, the fallback is an `http` hook to a small local server
  started at SessionStart, which would cost a few ms per batch. It's a design change, so it's
  deferred.

## Tools added for this sprint

- `scripts/live.py --no-plugin` gives a plugin-off baseline run of the same task, for the Medium
  cost overhead target (NFR-1, at most 10%).
- `scripts/bench_capture.py --event <Event>` measures any hook end to end.

## Results (Oct 8)

Built: delta injection (INJ-1, INJ-2), compaction digest (INJ-3), claim extraction (VER-1), BM25
candidates, Tier 1 and final labels (VER-2, VER-3), turn reports, summary line, `/qlaudified report`,
claims in `provenance.csv` (REP-2..4), inline markers via MessageDisplay (REP-1), 5 seed tasks with
ground-truth TOML and 5 live recordings. 178 free tests pass; ruff and mypy are clean.

| Check | Result |
| --- | --- |
| PostToolUse p95 with injection (NFR-3) | 270 ms (target 300) |
| MessageDisplay p95 | 254 ms: ~31 ms of marker work over the 223 ms floor |
| Stop p95 (NFR-5) | 267 ms end to end; 160 ms in process for 20 claims over 500 spans (target 5 s) |
| Medium cost overhead (NFR-1) | −0.1% mean across the 5 seed tasks, 2 runs on and 2 off each (within noise; target ≤ 10%) |
| Live spend | $0.073 for 20 seed runs |

- **Dropped qualifier caught live on "pending", not "estimated".** One of the two plugin-off
  seed-conflict answers dropped "pending QA sign-off" and "tentatively", and offline verification
  flagged both. Both plugin-on answers kept them. Haiku kept "estimated" in all 4 seed-hedged
  runs, so the "estimated" case is proven in contract and seed tests, not live.
- In `claude -p`, the JSON `result` carries the **marked** text, so the eval must strip markers
  (`text.clean` does this).
- `/compact` works as a `-p --resume` step. Multi-step tasks need the transcript, so `live.py`
  keeps it for them.
- Fixed after live runs: clause splitting dropped a hedge that appeared later in the same sentence
  (hedges now count across the whole sentence), and dates without a year ("November 18") are now
  parsed.

Left for the user: set up the stable copy for dogfooding (testing.md) after committing, then tag.
