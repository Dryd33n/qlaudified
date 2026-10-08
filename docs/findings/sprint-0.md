# Sprint 0 findings (Oct 9–11, 2026)

Results of the hook spike. Runbook: `spike/README.md`. Raw data: `docs/findings/data/`.

Environment: Claude Code 2.1.294 · Windows 11 Pro · Python 3.12.4 · macOS: CI only (`spike` workflow, no Mac available)

## Found during setup (Oct 8)

- **The Windows dev machine's Python was below the 3.10 floor.** `python` was the Microsoft Store
  stub and `py -3` gave 3.7.5. 3.12.4 is now installed. Users will hit the same trap, so the
  configurable Python command and a startup check stay in.
- **The plugin root path contains a space** (`C:\Users\<name> <surname>\...`). Shell-form hooks must
  quote `${CLAUDE_PLUGIN_ROOT}`; exec form needs no quoting.
- **Exec-form syntax** (hooks docs): `"command": "py", "args": ["-3", "${CLAUDE_PLUGIN_ROOT}/x.py"]`.
  With `args` present there is no shell, and placeholders are substituted per arg. On Windows,
  `command` must be a real `.exe`. `make_hooks.py --exec` writes this form. Confirmed live below.
- **`MessageDisplay` can rewrite what's shown** (hooks docs): `hookSpecificOutput.displayContent`
  replaces the on-screen text. It's display-only (the transcript and Claude keep the original), and
  the default timeout is 10 s.
- **`--max-turns` is not listed in `claude --help`**, but it's still accepted (a live run passed).
- **`--bare`** also exists ("skip hooks ... LSP, plugin sync"); not yet compared with `--safe-mode`.
- **The isolated config dir needs one `/login`.** The first live run failed in 2.2 s with "Not
  logged in · Please run /login". After `CLAUDE_CONFIG_DIR=~/.claude-qlaudified-test claude` and
  `/login`, the login persists.

## Live batch (Oct 8, haiku, `scripts/live.py`, about $0.06 in total)

| Run | Hooks | Result |
| --- | --- | --- |
| `inject` (`QLAUDIFIED_PROBE_INJECT=1`) | shell, `py -3` | Line seen 3× (SessionStart, Glob, Read), labelled "PostToolUse:Read hook additional context" |
| `repo` (Grep + Bash) | shell, `py -3` | Payloads below; Grep also matched the probe's own log folder |
| `web` (WebFetch + WebSearch) | shell, `py -3` | WebFetch gives only the summary; the raw page isn't in the payload |
| `notes` + `QLAUDIFIED_PROBE_NESTED=1` | shell, `py -3` | Nested `claude -p --safe-mode` from Stop: rc 0, 2.6 s, $0.0004 |
| `notes` | exec, `py` + `-3` | All 7 events fired on Python 3.12.4; spaced plugin root unquoted |
| `notes` | exec, `python` | All fired, but on **Store Python 3.9** (`WindowsApps\PythonSoftwareFoundation...`) |

### Payload map (PostToolUse, 2.1.294)

Common keys: `session_id`, `transcript_path`, `cwd`, `prompt_id`, `tool_use_id`, `tool_name`,
`tool_input`, `tool_response`, `duration_ms`, `effort`, `permission_mode`, `hook_event_name`.

| Tool | Locator | Text | Line numbers |
| --- | --- | --- | --- |
| Read | `tool_response.file.filePath` (absolute, backslashes, 8.3 short form under `%TEMP%`) | `tool_response.file.content`, **no** line-number prefixes | `file.startLine`, `numLines`, `totalLines` |
| Grep (content) | `tool_input.path`; a relative path on each content line | `tool_response.content`: `rel\path:line:text` lines; `numFiles` is 0 in this mode | in each content line (`-n`) |
| Bash | `tool_input.command` only | `tool_response.stdout`, `stderr` | none |
| WebFetch | `tool_input.url`, `tool_response.url`, `code` | `tool_response.result` = the small model's answer to `tool_input.prompt` (1 KB of a 315 KB page); raw size in `bytes` | none |
| WebSearch | `tool_input.query` | `tool_response.results[].content[]` = `{title, url}`; no snippets seen | none |
| Glob, ToolSearch | — | also fire PostToolUse with matcher `*`, so capture must filter by tool name | — |
| MCP | `tool_name` = `mcp__<server>__<tool>`; `tool_input` as sent | `tool_response` is a **list** of content blocks `[{type: "text", text}]`, not a dict (35 KB for one Docs `guide` call) | none |

Other events:
- **Stop** carries `last_assistant_message` and `stop_hook_active`. VER-1 needs no transcript
  parsing, and the flag gives the one-retry cap its guard.
- **MessageDisplay** carries `delta`, `index`, `final`, `message_id` and `turn_id`. Every headless
  answer so far arrived as one delta (`index 0`, `final true`), so streaming batches still need an
  interactive look.
- **Env paths** (`CLAUDE_PLUGIN_ROOT`, `CLAUDE_CONFIG_DIR`, `CLAUDE_PLUGIN_DATA`) use forward
  slashes; payload paths use backslashes.

### Recording notes

- With `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`, `-p` sessions write no transcript. `live.py --record`
  leaves it unset.
- Transcripts carry account data even from the isolated config dir: the user's email, the claude.ai
  connector list, and a 66 KB system-prompt snapshot. `collect.py` now keeps only user, assistant
  and system lines plus `hook_*` attachments. It also scrubs emails, 8.3 short paths and mangled
  paths, and renames transcripts.
- **`CLAUDE_CONFIG_DIR` does not isolate account-level claude.ai connectors.** That matters for
  eval baselines.

## Interactive session (Oct 8, haiku, `interactive-windows` recording)

- **MessageDisplay streams one paragraph per delta.** A 4-paragraph answer came as 4 deltas of
  ~500 chars, ~1 s apart (`index` 0–3, `final` only on the last). A list came one item per delta.
  The probe's handler took < 1 ms each.
- **Stop can fire before the last MessageDisplay.** Seen once (subagent turn: Stop 12:52:21, final
  delta after it). Verdicts from Stop can't be relied on while deltas are still being shown.
- **Compaction confirmed:** `PreCompact` (`trigger: manual`), then `SessionStart` with
  `source: compact` (keys include `model`). After compaction Claude still knew "$4.2M, estimated,
  preliminary" from the summary.
- **Subagent tool calls carry `agent_id` and `agent_type`** on PostToolUse (CAP-6 works). Main-agent
  calls have neither.
- **SubagentStop fires after every turn** for internal helper agents (`agent_type` empty: prompt
  suggestions, the compaction summarizer). Only the real subagent had `agent_type: Explore`. Filter
  on a non-empty `agent_type`.
- **No MCP payload yet.** Claude loaded `mcp__claude_ai_Claude_Docs__query` with ToolSearch but
  declined to call it (it needs a doc ID). `Artifact` is a built-in tool, not MCP. All payloads
  now include `scratchpad_dir`.

## Checklist

| # | Probe | Result | Notes |
| --- | --- | --- | --- |
| 1 | PostToolUse payloads: Read, Grep, Bash, WebFetch, WebSearch, MCP | **done** | Payload map above; MCP from `mcp__claude_ai_Claude_Docs__guide` (Oct 8, interactive) |
| 2 | `additionalContext` from PostToolUse reaches Claude | **confirmed** | Seen verbatim, labelled as hook output, checked against the file. A wrong path made Claude refuse it as a separate source |
| 3 | MessageDisplay: batch size, latency, can it rewrite text | **confirmed** | One paragraph (or list item) per delta, ~1 s apart; rewrite via `displayContent` documented. Go on markers from span matching per delta; no-go on verdict-based markers |
| 4 | SessionStart `compact` after manual `/compact` | **confirmed** | `PreCompact` (manual) then `SessionStart source: compact` |
| 5 | Nested `claude -p --safe-mode` from a hook, Pro login, startup time | **confirmed** | Haiku 2.6–2.8 s wall after the first call (~0.9 s API, $0.00025); sonnet 3.1–4.2 s, $0.004. Fixed CLI overhead ~1.7 s. Default small model: **haiku** |
| 6 | Windows: command form, `python` vs `py -3`, backslash paths | **confirmed** | Exec form works; bare `python` hits the Store 3.9 alias; 8.3 short paths; mixed separators |
| 7 | macOS: same probes | changed | CI only (`spike` workflow): startup timing and a payload smoke test; needs a push to run |
| 8 | Name on GitHub and PyPI | **free** | Free on PyPI and as a GitHub user/org; the only repo with the name is ours |
| 9 | Python hook startup time on Windows | done | `py -3` p50 102 ms / p95 113 ms; python.exe called directly p50 79 ms. The probe's own work is under 2 ms. (The `python` row in `startup.jsonl` is misleading: a child of 3.12 finds 3.12 first) |
| 10 | Separate `CLAUDE_CONFIG_DIR` keeps its login | **confirmed** | After one `/login`; timing run rc 0 |
| 11 | 4–6 recorded sessions in `tests/sessions/` | **done (5)** | `notes`, `inject`, `repo`, `web`, `interactive` (streaming, `/compact`, subagent) on Windows |

## Design risks

| Risk (design.md) | Status | Evidence / change |
| --- | --- | --- |
| Markers need verdicts that don't exist yet while streaming | **confirmed** | Deltas are shown paragraph by paragraph, and Stop can even fire after the last one. Markers come from span matching per delta; verdicts go to the report |
| `claude -p` startup takes seconds and uses plan limits | **confirmed** | ~1.7 s fixed overhead per call, 2.6 s in total for haiku. Keep it to one batched call at Stop, never one per tool call |
| Windows hook quirks (backslash paths, PowerShell vs Git Bash) | **changed** | The shell question goes away with exec form. New: bare `python` resolves to the Store alias (3.9); `%TEMP%` paths arrive in 8.3 form; env paths use `/` and payloads `\`. Normalize with long-path expansion, not just separators |
| Re-fetched page differs from what WebFetch saw | **changed** | WebFetch's payload has no raw text, only the summary and `bytes`. The shadow re-fetch (CAP-3) is the only raw source; compare its size to `bytes` instead of a hash |
| Stored spans carry injected instructions | **confirmed** | New variant: Grep matched the probe's own log folder (hidden folders aren't skipped), so the store can capture itself. Exclude `.claude/.qlaudified/` from capture |
| Rule-based claim splitting misses compound claims | noted | `repo` answer: "syncs every 900 seconds, which is 15 minutes" drops "roughly" inside a compound sentence. A good seed case |
| Stop retry loops or annoys | deferred | High mode, Sprint 4. `stop_hook_active` in the Stop payload gives the loop guard |

## Decisions out of this spike

- Hook command form: **exec form** (`command` + `args`), no shell.
- Python command default: **Windows `py` with `-3`** (accepted Oct 8, #6); macOS `python3`
  (confirm in the CI run).
  Hooks check `sys.version_info >= (3, 10)` and log a clear error instead of failing silently.
- Default sidecar model: **haiku**.
- Minimum Claude Code version: **2.1.294** (the only version tested).
- Inline markers approach (REP-1): **span matching per MessageDisplay delta**, rewritten via
  `displayContent` (display-only). Claim verdicts go to the report, not the markers.
- Name: **qlaudified**.

## Still to do (interactive)

- [x] #1 MCP: one session that actually calls an MCP tool
- [x] #3 MessageDisplay streaming
- [x] #4 `/compact`
- [x] Compaction and subagent recording (`interactive-windows`)
- [ ] #7: push and run the `spike` workflow for macOS

## Before Sprint 1

- [x] Install Python 3.12+ (3.12.4 installed Oct 8)
- [x] `pytest -q -m "not live"` runs on the new interpreter (Oct 8: 33 passed, 1 deselected)
