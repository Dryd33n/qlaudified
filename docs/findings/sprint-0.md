# Sprint 0 findings (Oct 9–11, 2026)

Results of the hook spike. Runbook: `spike/README.md`. Raw data: `docs/findings/data/`.

Environment: Claude Code 2.1.294 · Windows 11 Pro · macOS: _todo_

## Already found during setup (Oct 8)

- **Python on the Windows dev machine is below the 3.10 floor.** `python` is the Microsoft Store
  stub (fails with "Permission denied" from Git Bash); `py -3` resolves to 3.7.5 (Visual Studio's
  bundled interpreter). No 3.10+ is installed. Spike scripts are written for 3.7 so they run today;
  install 3.12+ (python.org installer, with the `py` launcher) before Sprint 1. This also confirms
  users will hit the same trap, so the configurable Python command and a startup check stay in.
- **The plugin root path contains a space** (`C:\Users\Dryden Bryson\...`), so hook commands must
  quote `${CLAUDE_PLUGIN_ROOT}`. The probe does; check it works.
- **No local example of exec-form hooks.** All installed plugins use a shell string (`sh "..."`).
  Confirm the exec-form syntax this Claude Code version supports, or fall back to a quoted string.
- **`--max-turns` is not listed in `claude --help`** (2.1.294); `--safe-mode`, `--plugin-dir` and
  `--permission-prompts none` are. Confirm `--max-turns` still works for `scripts/live.py`.
- **`--bare`** also exists ("skip hooks ... LSP, plugin sync"); compare with `--safe-mode` for the
  nested sidecar call.

## Checklist

| # | Probe | Result | Notes |
| --- | --- | --- | --- |
| 1 | PostToolUse payloads: Read, Grep, Bash, WebFetch, WebSearch, MCP | | where text, paths, line numbers live |
| 2 | `additionalContext` from PostToolUse reaches Claude | | how a provenance line is treated |
| 3 | MessageDisplay: batch size, latency, can it rewrite text | | go/no-go on inline markers |
| 4 | SessionStart `compact` after manual `/compact` | | |
| 5 | Nested `claude -p --safe-mode` from a hook, Pro login, startup time | | default small model: |
| 6 | Windows: command form, `python` vs `py -3`, backslash paths | | |
| 7 | macOS: same probes | | |
| 8 | Name on GitHub and PyPI | | |
| 9 | Python hook startup time on Windows | | |
| 10 | Separate `CLAUDE_CONFIG_DIR` keeps its login | | |
| 11 | 4–6 recorded sessions in `tests/sessions/` | | |

## Design risks

Mark each **confirmed**, **changed** or **retired**, with the evidence.

| Risk (design.md) | Status | Evidence / change |
| --- | --- | --- |
| Markers need verdicts that don't exist yet while streaming | | |
| `claude -p` startup takes seconds and uses plan limits | | |
| Windows hook quirks (backslash paths, PowerShell vs Git Bash) | | |
| Re-fetched page differs from what WebFetch saw | | |
| Stored spans carry injected instructions | | |
| Rule-based claim splitting misses compound claims | | (measured in Sprint 2+; note anything seen) |
| Stop retry loops or annoys | | |

## Decisions out of this spike

- Hook command form:
- Python command default (Windows / macOS):
- Default sidecar model:
- Minimum Claude Code version:
- Inline markers approach (REP-1):
- Name:
