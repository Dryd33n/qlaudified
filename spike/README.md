# Sprint 0 spike runbook (Oct 9–11)

Throwaway probes that confirm the hooks behave as `docs/design.md` assumes. Write results into
`docs/findings/sprint-0.md`; raw timing data lands in `docs/findings/data/`.

Everything here runs on Python 3.7+ (the probe is what Claude Code launches, so it must run on
whatever `py -3` / `python3` resolves to). Use `py -3` on Windows, `python3` on macOS.

**Never** load `spike/probe` in the session you're developing in. Use a separate terminal, and
preferably the isolated config dir: `CLAUDE_CONFIG_DIR=~/.claude-qlaudified-test`.

## 0. Setup

```sh
py -3 spike/make_hooks.py                 # writes spike/probe/hooks/hooks.json
```

If Claude Code complains about the `MessageDisplay` key, rerun with `--no-message-display` and record
that in the findings. To test the bare `python` command, use `--python python`.

## 1. Payload shapes (Read, Grep, Bash, WebFetch, WebSearch, MCP)

Interactive, in a scratch folder (copy `tests/sandbox/notes/` somewhere):

```sh
claude --plugin-dir <repo>/spike/probe
```

Ask it to read a file, grep for "estimated", `cat` a file via Bash, WebFetch a docs page, WebSearch
something, and call any one MCP tool. Then inspect `.qlaudified-probe/<session_id>/events.jsonl`:
for each tool, note where the output text, file path and line numbers live in `tool_response`, and
whether Read output carries line-number prefixes.

## 2. Does additionalContext reach Claude?

```sh
QLAUDIFIED_PROBE_INJECT=1 claude --plugin-dir <repo>/spike/probe
```

(PowerShell: `$env:QLAUDIFIED_PROBE_INJECT=1` first.) After one Read, ask Claude: "What provenance
lines have you seen, verbatim?" The probe injects
`[S1 notes/q3-update.md L3] Q3 revenue 4.2M USD; source says: estimated, preliminary`.
Note whether it's seen, how it's labelled in the transcript, and whether Claude treats it as a
possible prompt injection.

## 3. MessageDisplay

Look at the MessageDisplay records: how many fire per answer (batch size), the gap between them
(`ts`, `elapsed_ms`), and what fields hold the text. Decide go/no-go on inline markers from span
matching alone, and whether the hook can rewrite the displayed text at all.

## 4. Compaction

In a session with the probe, read a few files, run `/compact`, then check for a `SessionStart`
record whose payload `source` is `compact`. With `QLAUDIFIED_PROBE_INJECT=1`, ask whether the line
is visible after compaction.

## 5. Nested `claude -p` and the default small model

```sh
py -3 spike/time_claude_p.py --models haiku sonnet --runs 3
py -3 spike/time_claude_p.py --config-dir ~/.claude-qlaudified-test --runs 1
```

The second line checks a separate config dir keeps its login (log in once inside it if asked).
Then from inside a hook: run a session with `QLAUDIFIED_PROBE_NESTED=1` and read the `nested`
field on the Stop record (timing, return code, and that no probe events recursed from it).

## 6. Python startup on Windows

```sh
py -3 spike/time_startup.py --runs 20
```

## 7. Name check

```sh
py -3 spike/check_name.py qlaudified
```

## 8. Recording sessions for the simulator (4–6)

Headless recordings use the isolated runner with the probe as the plugin:

```sh
py -3 scripts/live.py notes --plugin-dir spike/probe
py -3 spike/collect.py <sandbox>/.qlaudified-probe/<session_id> notes --sandbox <sandbox>
```

Scenarios from `docs/testing.md`: summarize a notes folder, grep this repo, WebFetch a docs page, a
long task forced through `/compact` (interactive), a task that spawns a subagent (interactive;
`-p` disables built-in agents). Record the path-heavy ones on both Windows and macOS.
