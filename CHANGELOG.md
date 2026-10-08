# Changelog

Three lines per sprint, written at the Sunday demo.

## Sprint 1 · Foundations and capture (Oct 12–18, 2026; done Oct 8)

- Capture works end to end: live sessions on notes and a repo fill `provenance.csv` with one span per fact, normalized numbers and dates, and hedge words; `/qlaudified mode` saves and overrides modes.
- Hook overhead p95 is 251–258 ms (target 300) after adding `-S` and a lazy `tomllib` import; the Python floor is now 3.11.
- Fixed while building: a SQLite setup race between parallel hooks, subagent spans losing their agent ID, and WebFetch's own note being read as page content.

## Sprint 0 · Spike (Oct 9–11, 2026)

- Hooks behave as designed: payloads mapped for every tool type, `additionalContext` reaches Claude, compaction and subagent events confirmed; 5 scrubbed Windows recordings in `tests/sessions/`.
- Decisions: `py -3` on Windows and `python3` on macOS (one shell-form hook line; exec form was dropped in Sprint 1 prep), haiku as the sidecar model, and inline markers from per-paragraph span matching (verdicts go to the report).
- Surprises: WebFetch gives no raw text (re-fetch is required), Windows sends 8.3 short paths, bare `python` can be the Store's 3.9, and the store must exclude itself from capture.
