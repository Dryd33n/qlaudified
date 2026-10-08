# Sprint 1 results (Oct 8, 2026)

Plugin skeleton, mode command and capture into the store. Issues #11–#17.

Environment: Claude Code 2.1.295 · Windows 11 Pro · Python 3.12.4. macOS runs in CI.

## Demo: "a session fills provenance.csv from local docs and code"

Live smoke tests (`pytest -m live tests/live`, haiku, isolated sandboxes): **3 passed**, $0.0055 in total.

| Task | Result |
| --- | --- |
| `notes` (Read ×2) | 7 spans, one per fact line. `q3-update.md L3`: `4200000 USD`, qualifiers `estimated; preliminary`. `launch-memo.md L3`: `2026-11-18`, `tentatively`. `L4`: `12 USD`, `expected to; subject to change` |
| `repo` (Grep, then `cat` via Bash) | Grep lines as `ledger/config.py L6`, `ledger/sync.py L5` (`may; usually`). The `cat` was upgraded to file spans `ledger/config.py L1`, `L3-L6` (`900 s`, `roughly`) |
| `mode` (`/qlaudified mode high`) | The skill ran the CLI and wrote `mode = "high"` to `config.toml` |

No `errors.log` in any run. The same results come from replaying the Sprint 0 recordings
(`tests/replay`), so they're checked on every CI run for free.

## Latency (NFR-3: capture p95 ≤ 300 ms)

`scripts/bench_capture.py` runs the real hooks.json command through Git Bash, 30 runs per fixture,
with a new span on every run:

| Step | p50 | p95 |
| --- | --- | --- |
| First version | 288 ms | 324 ms (**miss**) |
| + `-S` (skip `site`) and lazy `tomllib` | 238 ms | 251–258 ms (**met**) |

The remaining time breaks down as: Git Bash ~45 ms, `command -v py` ~10 ms, the `py` launcher ~25 ms,
interpreter ~30 ms, imports ~85 ms, capture and SQLite ~20 ms. In the live runs, in-process time
was 80–160 ms per PostToolUse; the first call creates the database. The headroom left is about 45 ms.
Dropping `dataclasses` (~25 ms of `inspect` import) is the next lever if Sprint 2 needs it.

## Found while building

- **Parallel hooks raced to set up a new database.** `PRAGMA journal_mode = WAL` and schema creation
  ignore the busy timeout, so 6 parallel writers saw "database is locked". Setup now retries and
  skips steps already done; the threaded test passes repeatedly.
- **A subagent re-reading a file got the main agent's span.** Dedupe was on source, locator and
  hash, so the subagent's ID was lost. Spans are now unique per agent (CAP-6).
- **WebFetch appends a note to long pages** ("[WebFetch note: this page's text is 108931 characters
  long…]"). It produced fake numbers, so capture strips it.
- **`PATH` can find WSL's `bash.exe` before Git Bash.** Claude Code uses Git Bash, and the
  benchmark does the same.
- **Plugin skill, not `commands/`.** `${CLAUDE_PLUGIN_ROOT}` is only substituted in plugin skills.
  The `` !`...` `` line runs the CLI before Claude sees anything, and must exit 0 or the skill
  aborts, so `hooks/cli.py` always exits 0.
- **Python floor raised to 3.11** for `tomllib`. `run.py` and `cli.py` still run on old Pythons
  to explain the floor: a `systemMessage` at each session start and one line in `errors.log`.
  Checked with Python 3.7.

## Not done / carried forward

- macOS has only been checked in CI (the `ci` and `spike` workflows), not in a live session.
- `MessageDisplay` isn't registered yet: it would start Python for every streamed paragraph with
  nothing to do until Sprint 2's markers.
