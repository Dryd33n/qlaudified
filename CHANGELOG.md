# Changelog

Three lines per sprint, written at the Sunday demo.

## Sprint 0 · Spike (Oct 9–11, 2026)

- Hooks behave as designed: payloads mapped for every tool type, `additionalContext` reaches Claude, compaction and subagent events confirmed; 5 scrubbed Windows recordings in `tests/sessions/`.
- Decisions: exec-form hooks with `py -3` on Windows and `python3` on macOS, haiku as the sidecar model, and inline markers from per-paragraph span matching (verdicts go to the report).
- Surprises: WebFetch gives no raw text (re-fetch is required), Windows sends 8.3 short paths, bare `python` can be the Store's 3.9, and the store must exclude itself from capture.
