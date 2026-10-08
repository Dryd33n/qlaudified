# Sprint 0 findings (Oct 9–11, 2026)

Results of the hook spike. Runbook: `spike/README.md`. Raw data: `docs/findings/data/`.

Environment: Claude Code 2.1.294 · Windows 11 Pro · macOS: CI only (`spike` workflow, no Mac available)

## Already found during setup (Oct 8)

- **Python on the Windows dev machine is below the 3.10 floor.** `python` is the Microsoft Store
  stub (fails with "Permission denied" from Git Bash); `py -3` resolves to 3.7.5 (Visual Studio's
  bundled interpreter). No 3.10+ is installed. Spike scripts are written for 3.7 so they run today;
  install 3.12+ (python.org installer, with the `py` launcher) before Sprint 1. This also confirms
  users will hit the same trap, so the configurable Python command and a startup check stay in.
- **The plugin root path contains a space** (`C:\Users\Dryden Bryson\...`), so hook commands must
  quote `${CLAUDE_PLUGIN_ROOT}`. The probe does; check it works.
- **No local example of exec-form hooks.** All installed plugins use a shell string (`sh "..."`).
  The hooks docs settle the syntax: `"command": "py", "args": ["-3", "${CLAUDE_PLUGIN_ROOT}/x.py"]`.
  With `args` present there is no shell, and placeholders are substituted per arg, so no quoting
  is needed. On Windows, `command` must be a real `.exe`. `make_hooks.py --exec` writes this form.
  It still needs a live check on 2.1.294.
- **The docs say `MessageDisplay` can rewrite what's shown.** `hookSpecificOutput.displayContent`
  replaces the on-screen text. It's display-only (the transcript and Claude keep the original), and
  the default timeout is 10 s. That makes display-only inline markers plausible; probe 3 confirms
  the batching and latency.
- **`--max-turns` is not listed in `claude --help`** (2.1.294); `--safe-mode`, `--plugin-dir` and
  `--permission-prompts none` are. Confirm `--max-turns` still works for `scripts/live.py`.
- **`--bare`** also exists ("skip hooks ... LSP, plugin sync"); compare with `--safe-mode` for the
  nested sidecar call.

## First live run (Oct 8, `notes`, shell-form hooks)

- Failed in 2.2 s at $0: the isolated config dir isn't logged in ("Not logged in · Please run
  /login"). Fix: run `CLAUDE_CONFIG_DIR=~/.claude-qlaudified-test claude` once and `/login`.
- Still useful: the plugin loaded via `--plugin-dir`, and the shell-form hook with a quoted,
  space-containing `${CLAUDE_PLUGIN_ROOT}` ran. The events were SessionStart (`source: startup`),
  UserPromptSubmit, MessageDisplay and SessionEnd (`reason: other`), each under 2 ms in the probe.
- MessageDisplay payload fields: `prompt_id`, `turn_id`, `message_id`, `index`, `final`, `delta`.
  Non-ASCII arrives as valid UTF-8 on stdin.
- After `/login` in the isolated config dir, the rerun passed: 3 turns, 5.3 s, $0.0048 on haiku.
  So `--max-turns` is still accepted on 2.1.294, even though `--help` doesn't list it.

## Checklist

| # | Probe | Result | Notes |
| --- | --- | --- | --- |
| 1 | PostToolUse payloads: Read, Grep, Bash, WebFetch, WebSearch, MCP | | where text, paths, line numbers live |
| 2 | `additionalContext` from PostToolUse reaches Claude | | how a provenance line is treated |
| 3 | MessageDisplay: batch size, latency, can it rewrite text | | go/no-go on inline markers |
| 4 | SessionStart `compact` after manual `/compact` | | |
| 5 | Nested `claude -p --safe-mode` from a hook, Pro login, startup time | | default small model: |
| 6 | Windows: command form, `python` vs `py -3`, backslash paths | | |
| 7 | macOS: same probes | changed | CI only (`spike` workflow): startup timing + payload smoke; no interactive recordings |
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

## Before Sprint 1

- [ ] Install Python 3.12+ (python.org installer, with `py` launcher); `py -0p` shows only 3.7 today
- [ ] `pytest -q -m "not live"` runs on the new interpreter
