# qlaudified

A Claude Code plugin for research work. As Claude works, a sidecar agent (the Provenance
Administrator) records every critical fact: what it says, where it came from, how the source
qualified it ("estimated", "may", "tentative"), whether that qualifier survived Claude's use of it,
and how it shaped the answer. The record is a rolling, read-only `provenance.csv`, closed by a
provenance report. Optionally it's fed back into Claude's loop, so qualifiers survive long tasks.

**Status:** pre-alpha, mid-redesign. Sprints 0–4 built design revision 1 (rule-based capture and
verification, refeeding in Medium, a retry in High, a 20-task eval harness). On Oct 8 the design
returned to its original idea (revision 2: the sidecar's provenance record is the core and
refeeding is the hypothesis). Sprint 5 rebuilds the core; Sprint 6 runs the study and ships v1.

| Mode | What it does |
| --- | --- |
| Low | Records provenance (sidecar + rules); nothing reaches Claude |
| Medium | Records and feeds the record back into the loop |
| High | Medium, plus one retry when the answer drops a qualifier or contradicts a source |

- Design and requirements: [docs/design.md](docs/design.md)
- Sprint plan: [docs/sprint-plan.md](docs/sprint-plan.md)
- Testing and dev workflow: [docs/testing.md](docs/testing.md)
- Evaluation report (lab report; main study pending): [docs/evaluation.md](docs/evaluation.md)
- Findings: [Sprint 0](docs/findings/sprint-0.md) · [Sprint 1](docs/findings/sprint-1.md) · [Sprint 2](docs/findings/sprint-2.md) · [Sprint 3](docs/findings/sprint-3.md) · [Sprint 4](docs/findings/sprint-4.md) · spike runbook: [spike/README.md](spike/README.md)

## Try it

Requires Python 3.11+, and Git for Windows on Windows. Load the plugin for one session from a
project folder (not this repo's own working copy):

```sh
claude --plugin-dir /path/to/qlaudified
```

Then (these describe what's built today, revision 1; Sprint 5 changes Low and Medium as above):
- `/qlaudified mode` shows the mode; `/qlaudified mode high` saves it for the project, and
  `/qlaudified mode low --session` changes it for this session only.
- `/qlaudified report` prints the last answer's claim-by-claim report; `--deep` adds one LLM
  call (haiku via `claude -p`, or Ollama) for the claims the rules couldn't settle.
- `/qlaudified nli install` downloads the optional NLI model (needs `pip install "qlaudified[nli]"`).
- `/qlaudified csv` opens this session's `provenance.csv`; `--path` prints its location.
- Everything is stored under `.claude/.qlaudified/` in the project, which ignores itself in git.

## Progress

| Sprint | Goal | Status |
| --- | --- | --- |
| 0 · Oct 9–11 | Prove the hooks behave as the design assumes | Done: [findings](docs/findings/sprint-0.md) |
| 1 · Oct 12–18 | Plugin skeleton, mode command, capture into the store | Done: [results](docs/findings/sprint-1.md) |
| 2 · Oct 19–25 | Medium mode end to end | Done: [results](docs/findings/sprint-2.md) |
| 3 · Oct 26–Nov 1 | Web sources, NLI and LLM tiers | Done: [results](docs/findings/sprint-3.md) |
| 4 · Nov 2–8 | High mode and the eval harness | Done: [results](docs/findings/sprint-4.md) |
| 5 · Nov 9–15 | The Provenance Administrator (design revision 2) | Next |
| 6 · Nov 16–22 | Study, README, v1 tag | |

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
eval/                        Fernwick corpus, tasks, runner, scorer
scripts/live.py              isolated live smoke runs
scripts/bench_capture.py     end-to-end hook latency (NFR-3)
spike/                       Sprint 0 throwaway probes
tests/                       unit, contract, replay, live
```

## License

MIT
