# Changelog

Three lines per sprint, written at the Sunday demo.

## Sprint 5 · The Provenance Administrator (Nov 9–15, 2026; done Oct 8)

- The core runs on revision 2: live, a 4-step decay task filled `provenance.csv` step by step (one ~4.5 s, ~$0.0005 haiku call per qualifying step), Medium refed the facts (Claude cited `[F1]`), and every Stop wrote its report.
- Benchmarks: PostToolUse p95 364 ms (NFR-3 ≤ 400 ms, after cutting `dataclasses` and `traceback` from the hook path), sidecar step ~6.5 s (NFR-4 ≤ 10 s), ~$0.0013 per qualifying step.
- The 14-run decay dry run scored end to end: Medium kept 14/14 qualifiers, Low 10/14 (too few runs to mean anything yet); the live run also caught digits in file names being read as figures.

## Design revision 2 (Oct 8, 2026)

- Back to the original idea: a Provenance Administrator sidecar records REQ-3.2 rows (claim, origin, hybrid resolution, qualifiers at the source and at first use, operational impact) for critical facts in a rolling, read-only `provenance.csv`; feeding it back into the loop is the hypothesis.
- Modes: Low records, Medium records and refeeds, High adds the retry. Facts are stored, never passages; time is accepted as a cost, tokens are minimized.
- Sprint 5 rebuilds the core; Sprint 6 runs the study (decay across steps, Medium vs Low) and ships v1 on Nov 22.

## Sprint 4 · High mode and eval harness (Nov 2–8, 2026; done Oct 8)

- High mode works: a background sidecar finds qualifiers the lexicon misses, and Stop blocks once with a factual problem list; live, Claude turned "Q3 revenue was $4.2M." into "an estimated $4.2M, based on preliminary figures".
- The eval is ready: 20 tasks (4 per type), a resumable runner (Off runs in Low mode), offline scoring; the 15-run haiku dry run produced the full results table for $0.07.
- Misses and fixes: High's cost overhead is +38% on haiku (NFR-2 says ≤ 20%; recheck on Sonnet), the sidecar once called "due on" a qualifier (it can no longer block), and "May 2027" was read as the hedge "may".

## Sprint 3 · Web sources and model tiers (Oct 26–Nov 1, 2026; done Oct 8)

- WebFetch pages are re-fetched in a detached process, so the raw text is the evidence; summary sentences that drop a page's qualifier are reported, and failures mark the source `summarized-only`.
- Two optional tiers: NLI (quantized DeBERTa, ~20 ms per pair) and one batched LLM call per turn (`report --deep` in Medium, automatic in High); every verdict is labelled rules, NLI or LLM.
- Found: `async` hooks die with `claude -p`, WebFetch can't reach `http://localhost`, and replays must run offline.

## Sprint 2 · Medium mode end to end (Oct 19–25, 2026; done Oct 8)

- Medium works end to end with no model calls: delta injection, a post-compaction digest, inline `[S3]` markers, and Stop verification with reports.
- Medium's measured cost overhead is within noise (−0.1% across 5 seed tasks); hooks stay under 300 ms p95.
- Live, plugin-off answers dropped "pending" and the verifier flagged it; plugin-on answers kept their qualifiers.

## Sprint 1 · Foundations and capture (Oct 12–18, 2026; done Oct 8)

- Capture works end to end: live sessions on notes and a repo fill `provenance.csv` with one span per fact, normalized numbers and dates, and hedge words; `/qlaudified mode` saves and overrides modes.
- Hook overhead p95 is 251–258 ms (target 300) after adding `-S` and a lazy `tomllib` import; the Python floor is now 3.11.
- Fixed while building: a SQLite setup race between parallel hooks, subagent spans losing their agent ID, and WebFetch's own note being read as page content.

## Sprint 0 · Spike (Oct 9–11, 2026)

- Hooks behave as designed: payloads mapped for every tool type, `additionalContext` reaches Claude, compaction and subagent events confirmed; 5 scrubbed Windows recordings in `tests/sessions/`.
- Decisions: `py -3` on Windows and `python3` on macOS (one shell-form hook line; exec form was dropped in Sprint 1 prep), haiku as the sidecar model, and inline markers from per-paragraph span matching (verdicts go to the report).
- Surprises: WebFetch gives no raw text (re-fetch is required), Windows sends 8.3 short paths, bare `python` can be the Store's 3.9, and the store must exclude itself from capture.
