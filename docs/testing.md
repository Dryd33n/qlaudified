# Testing and dev workflow

Claude Code can test qlaudified without ever loading the code it is editing: most tests feed recorded hook JSON to plain Python, and only a thin layer starts a separate, isolated `claude -p` with the plugin.

> Exported from the living design doc. See `design.md` for requirements and `sprint-plan.md` for when each piece is built.

## Who runs what

Three Claude Code processes can be involved, and only the middle one loads the code under test.

*Diagram — "Only an isolated child session ever loads the plugin under test":*

- **Dev session** (Claude Code in the repo, no qlaudified loaded, edits code and runs tests) → *runs `live.py`* → **Test session** (`claude -p` in a temp folder, its own config dir, plugin = working copy) → *High mode* → **Sidecar call** (`claude -p --safe-mode`, no hooks or plugins, returns JSON verdicts).
- Dev session → *every change* → **pytest, layers 1–3** (fixture JSON into hooks, no Claude Code, free).
- Test session → *writes results* → **What the test checks** (store rows, turn report, transcript, cost ceiling).

The dev session never sees qlaudified's hooks; it launches the test session as an ordinary shell command and reads the files it leaves behind.

## Test layers

The first three layers need no Claude Code at all and run in seconds, so Claude Code can run them after every change. Hooks are just scripts that read JSON on stdin and print JSON, which makes them easy to test directly.

| Layer | What it checks | Needs a real session? | Cost | When it runs |
| --- | --- | --- | --- | --- |
| Unit | Core functions: normalization, lexicon, claim splitting, BM25, verifier tiers | No | Free, seconds | Every change, CI |
| Hook contract | Each hook script: recorded payload in, expected JSON out and expected store rows | No | Free, seconds | Every change, CI |
| Replay | A recorded session's event sequence through all hooks: deltas, digest, one-retry cap | No | Free, seconds | Every change, CI |
| Live smoke | Real `claude -p` in a sandbox with the plugin under test, 3–5 short scripted tasks | Yes, isolated | Plan usage, 1–3 min | Before merging hook changes |
| Eval | Full corpus × 3 live conditions | Yes, isolated | Heavy | Sprints 4–5 only |
| Manual | What only a human sees: inline markers in the terminal, command UX | You, interactively | Your time | Sunday sprint demo |

Model-dependent code (sidecar, tier 3) uses a `fake` backend in layers 1–3 that returns canned JSON, so tests stay deterministic and free.

## Recorded sessions as a simulator

A handful of real sessions, recorded once, stand in for live Claude in almost every test: a simulator plays them back through the hooks exactly as Claude Code would, for free and as often as needed.

1. **Record.** In Sprint 0, run 4–6 short real sessions on tasks pertinent to the project: summarize a notes folder, grep this repo, WebFetch a docs page, a long task forced through `/compact`, a task that spawns a subagent. A `record` hook on every event saves each under `tests/sessions/<name>/`: ordered hook payloads (`events.jsonl`), the transcript, raw fetched pages, and a snapshot of the sandbox files.
2. **Scrub.** Replace home paths and session IDs with placeholders; keep a Windows and a macOS recording of the path-heavy sessions.
3. **Simulate.** `qlaudified-sim tests/sessions/<name>` rebuilds the sandbox in a temp folder and pipes each event through the real hook entry points in order, with the environment variables Claude Code would set. Tests then assert the store, injected lines, compaction digest, Stop verdicts and report.
4. **Grow the library.** Every live smoke run and eval run is recorded the same way, so the set of simulated sessions grows without extra spending.

**What a recording can't show.** Claude's later steps in a recording were made without qlaudified's injections, so replay proves the plumbing and the verdicts, not whether injected provenance changes Claude's answer. Only live eval runs answer that.

**Drift check.** When Claude Code updates, one live smoke run re-records a session and fails if a field our hooks read has moved or disappeared.

## Live smoke tests

A live test starts a separate `claude -p` from a throwaway sandbox folder, with its own config directory, so neither your personal setup nor the dev session leaks into it, and it uses your plan login rather than an API key.

One wrapper script owns every flag, so Claude Code only ever runs `python scripts/live.py <task>`:

```
sandbox = copy of tests/sandbox/<task>/ into a temp folder

env:
  CLAUDE_CONFIG_DIR=~/.claude-qlaudified-test   # clean config: no personal hooks, plugins or settings
  CLAUDE_CODE_DISABLE_CLAUDE_MDS=1              # no CLAUDE.md files leak in
  CLAUDE_CODE_DISABLE_AUTO_MEMORY=1
  CLAUDE_CODE_SKIP_PROMPT_HISTORY=1             # test runs stay out of your history
  CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=1            # shorter system prompt
  CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1     # no subagents in -p
  CLAUDE_CODE_DISABLE_BUNDLED_SKILLS=1

claude -p "<task prompt>"
  --plugin-dir <repo working copy>
  --model haiku
  --max-turns 6
  --allowedTools "Read,Grep,Glob,Bash,WebFetch,WebSearch"
  --permission-prompts none
  --output-format json
```

- **Web tests:** `qlaudified.testing.webserver` serves saved pages from `tests/fixtures/web/` (plus `/paywall` and `/slow`). WebFetch itself won't fetch `http://localhost`, so live web tasks use public pages. Replays set `QLAUDIFIED_OFFLINE=1`: no re-fetch, no LLM.
- **Recording and steps:** `--record` keeps the transcript and sets `QLAUDIFIED_RECORD_DIR`, so the plugin logs every event and its own response; `--collect NAME` scrubs that into `tests/sessions/NAME-<os>/`. A `prompt.txt` with `---` lines runs each step in one session via `--resume` (used for `/compact`). `--no-plugin` gives the cost baseline.
- **One-time setup:** log in once inside the test config directory if Claude Code asks; after that, runs reuse it.
- **What the test asserts:** rows in the sandbox's `.claude/.qlaudified/` store, the saved turn report, the injected lines in the session transcript, and `total_cost_usd` staying under a ceiling.
- **The sidecar's own nested call** (`claude -p` from inside a hook) uses `--safe-mode`, which loads no hooks, plugins or CLAUDE.md, so it can't recurse into qlaudified.
- **Budget:** each smoke task is capped by `--max-turns` and a cost ceiling; the suite is 3–5 tasks and runs only on request or before merging hook changes.

## Keeping tests cheap on a Pro plan

The rule: every live run should be worth reusing, and anything that can be re-checked offline never touches Claude again.

**Spend fewer runs**

- **Record once, replay forever.** Every live run saves its full hook event stream as a new replay fixture. Live runs are needed again only when a hook's contract changes or Claude Code updates.
- **Score offline.** Agent transcripts are saved, so verifier changes are re-scored against old runs for free. The post-hoc eval condition is the Off runs verified offline, which removes a whole condition of live runs.
- **Sidecar off in tests.** Live smoke tests use the `fake` or Ollama backend; exactly one dedicated smoke task exercises the `claude-cli` sidecar.

**Make each run small**

- `--model haiku` for smoke tests; the hooks don't care which model calls the tools.
- A lean test config: clean `CLAUDE_CONFIG_DIR` (no MCP servers or plugins), `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=1`, `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` (no subagents in `-p`), `CLAUDE_CODE_DISABLE_BUNDLED_SKILLS=1`.
- Tiny sandboxes (a few files under 1 KB), one-sentence prompts that name the file, `--max-turns 4` to `6`.
- Run smoke tasks back to back so they reuse the prompt cache.

**Guard the budget**

- `scripts/live.py` and the eval runner append each run's `total_cost_usd` estimate to `eval/ledger.jsonl` and refuse to start once a daily cap you set is reached.
- Long eval batches set `CLAUDE_CODE_RETRY_WATCHDOG=1`, so hitting a usage limit means waiting, not a failed run.

**Your dev sessions cost more than the tests.** Use Sonnet for routine coding, `/clear` between unrelated tasks, keep `CLAUDE.md` short, run `pytest -q`, and tell Claude in `CLAUDE.md` not to open `tests/sessions/`, `tests/fixtures/` or `eval/corpus/` unless asked.

## Dogfooding without breaking the dev session

Never load the working copy into the session that is editing it: a half-written hook would fire on Claude Code's own tool calls and could break the session mid-edit.

- **Stable copy for daily use.** Keep a second checkout pinned to the last good tag (e.g. `~/tools/qlaudified-stable`) and load that one in your normal Claude Code sessions. Update it at the end of each sprint.
- **Dev session stays clean.** The Claude Code session working in the repo has no qlaudified loaded at all, or only the stable copy if you want provenance on your own research.
- **Hooks know when they're nested.** Claude Code sets `CLAUDE_CODE_CHILD_SESSION=1` in processes it spawns; qlaudified logs it so a report shows whether it ran inside a test.
- **Kill switch.** If a hook misbehaves in a real session, `/qlaudified mode low` turns it off, and `claude --safe-mode` starts a session with no plugins or hooks at all.

## Setting up the repo for Claude Code

A short `CLAUDE.md` and a few allow rules let Claude Code run the free tests on its own and ask before anything that spends plan usage.

**Draft `CLAUDE.md`**

```markdown
# qlaudified

Claude Code plugin (Python) that records source spans and verifies claims.
Spec: docs/design.md · Sprints: docs/sprint-plan.md · Testing: docs/testing.md

## Testing
- After any change: `pytest -q -m "not live"` (unit, hook contract, replay). Must pass.
- Hook scripts are tested by piping recorded JSON from tests/sessions and tests/fixtures.
- Live tests: only via `python scripts/live.py <task>`. Ask before running more than one.
- Never run the eval runner unless asked. It uses plan usage.
- Don't open tests/sessions/, tests/fixtures/ or eval/corpus/ unless the task needs it.

## Rules
- Never load this working copy as a plugin in the current session.
- Core code is standard library only; extras go behind [web] / [nli].
- Hooks must never raise: catch, log to .claude/.qlaudified/errors.log, exit 0.
- Hooks are one shell-form line: `py -3` if present, else `python3` (design.md, Hook command).
  Normalize paths: Windows sends backslashes and 8.3 short names.
- Injected context is plain facts, never instructions.
- Tag commits and issues with requirement IDs (CAP-1, VER-4, ...).
```

**Permissions** in `.claude/settings.json`: allow `Bash(pytest *)`, `Bash(python scripts/live.py *)` and `Bash(python -m qlaudified.testing *)`; leave `Bash(python eval/run.py *)` on ask.

**Project commands** for your own use: `/test` (layers 1–3 with a summary), `/smoke <task>` (one live task), and `/record <scenario>` (record a new session for the simulator).

## CI

GitHub Actions runs the free layers on every push, on `windows-latest` and `macos-latest`, across two Python versions; live tests stay local.

- **Every push and PR:** lint, type check, `pytest -m "not live"`, plus an install test of `pip install .` and `pip install .[nli]` on both OSes.
- **Hook smoke without Claude Code:** pipe each recorded payload through the real hook entry points as Claude Code would (the `py -3` / `python3` command from hooks.json), catching Windows path and quoting bugs.
- **Live tests in CI (optional, later):** possible with a token from `claude setup-token` stored as a secret, on a weekly schedule only, since every run draws on your plan.
