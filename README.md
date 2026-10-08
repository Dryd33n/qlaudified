# qlaudified

A Claude Code plugin that tracks where each claim in Claude's answer came from, and whether the source's
qualifiers ("estimated", "may", "tentative") survived the trip.

**Status:** pre-alpha. Sprints 0 and 1 are done: the plugin records every local retrieval as
spans in `provenance.csv`, but doesn't inject or verify anything yet. Sprint 2 (Medium mode end to
end, Oct 19–25) is next.

- Design and requirements: [docs/design.md](docs/design.md)
- Sprint plan: [docs/sprint-plan.md](docs/sprint-plan.md)
- Testing and dev workflow: [docs/testing.md](docs/testing.md)
- Findings: [Sprint 0](docs/findings/sprint-0.md) · [Sprint 1](docs/findings/sprint-1.md) · spike runbook: [spike/README.md](spike/README.md)

## Try it

Requires Python 3.11+, and Git for Windows on Windows. Load the plugin for one session from a
project folder (not this repo's own working copy):

```sh
claude --plugin-dir /path/to/qlaudified
```

Then:
- `/qlaudified mode` shows the mode; `/qlaudified mode high` saves it for the project, and
  `/qlaudified mode low --session` changes it for this session only.
- `/qlaudified csv` opens this session's `provenance.csv`; `--path` prints its location.
- Everything is stored under `.claude/.qlaudified/` in the project, which ignores itself in git.

## Progress

| Sprint | Goal | Status |
| --- | --- | --- |
| 0 · Oct 9–11 | Prove the hooks behave as the design assumes | Done: [findings](docs/findings/sprint-0.md) |
| 1 · Oct 12–18 | Plugin skeleton, mode command, capture into the store | Done: [results](docs/findings/sprint-1.md) |
| 2 · Oct 19–25 | Medium mode end to end | Next |
| 3 · Oct 26–Nov 1 | Web sources, NLI and LLM tiers | |
| 4 · Nov 2–8 | High mode and the eval harness | |
| 5 · Nov 9–15 | Ablation results, README, v1 tag | |

What Sprint 0 settled:
- Hooks use one command for both OSes: `py -3` on Windows, `python3` on macOS. Python 3.11+ is
  required, plus Git for Windows on Windows.
- WebFetch returns only a summary, so web sources need a separate re-fetch.
- Inline markers come from matching each streamed paragraph against stored sources; claim
  verdicts go to the report.
- Haiku is the default model for the nested verification call.

What Sprint 1 settled:
- Capture covers Read, Grep, Bash, PowerShell, WebFetch summaries, WebSearch results and MCP tools,
  with normalized numbers and dates and the hedge words each passage carries.
- Hook overhead is about 240 ms per tool call (p95 under 260 ms, against a 300 ms target).
- `/qlaudified` is a plugin skill that runs its command directly, so it costs no model turn.

## Development

```powershell
py -3 -m pip install -e ".[dev]"     # Windows; use python3 on macOS
py -3 -m pytest -q -m "not live"     # free test layers
```

## Layout

```
.claude-plugin/plugin.json   plugin manifest
hooks/hooks.json             hook registrations: py -3 if present, else python3
hooks/run.py                 single hook entry point: run.py <event>
hooks/cli.py, launch.sh      /qlaudified entry point and Python picker
skills/qlaudified/SKILL.md   /qlaudified mode | report | csv
qlaudified/                  Python package (standard library only)
eval/                        Fernwick corpus, tasks, runner (Sprints 2-5)
scripts/live.py              isolated live smoke runs
scripts/bench_capture.py     end-to-end hook latency (NFR-3)
spike/                       Sprint 0 throwaway probes
tests/                       unit, contract, replay, live
```

## License

MIT
