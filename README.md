# qlaudified

A Claude Code plugin that tracks where each claim in Claude's answer came from, and whether the source's
qualifiers ("estimated", "may", "tentative") survived the trip.

**Status:** pre-alpha. Sprint 0 (hook spike) is done; Sprint 1 (plugin skeleton and capture,
Oct 12–18) is next. Nothing here is usable yet.

- Design and requirements: [docs/design.md](docs/design.md)
- Sprint plan: [docs/sprint-plan.md](docs/sprint-plan.md)
- Testing and dev workflow: [docs/testing.md](docs/testing.md)
- Sprint 0 findings: [docs/findings/sprint-0.md](docs/findings/sprint-0.md) · runbook: [spike/README.md](spike/README.md)

## Progress

| Sprint | Goal | Status |
| --- | --- | --- |
| 0 · Oct 9–11 | Prove the hooks behave as the design assumes | Done: [findings](docs/findings/sprint-0.md) |
| 1 · Oct 12–18 | Plugin skeleton, mode command, capture into the store | Next |
| 2 · Oct 19–25 | Medium mode end to end | |
| 3 · Oct 26–Nov 1 | Web sources, NLI and LLM tiers | |
| 4 · Nov 2–8 | High mode and the eval harness | |
| 5 · Nov 9–15 | Ablation results, README, v1 tag | |

What Sprint 0 settled:
- Hooks run in exec form, with `py -3` on Windows and `python3` on macOS. Python 3.10+ is required.
- WebFetch returns only a summary, so web sources need a separate re-fetch.
- Inline markers come from matching each streamed paragraph against stored sources; claim
  verdicts go to the report.
- Haiku is the default model for the nested verification call.

## Development

```powershell
py -3 -m pip install -e ".[dev]"     # Windows; use python3 on macOS
py -3 -m pytest -q -m "not live"     # free test layers
```

## Layout

```
.claude-plugin/plugin.json   plugin manifest
hooks/hooks.json             hook registrations (empty until Sprint 1)
hooks/run.py                 single hook entry point: run.py <event>
commands/qlaudified.md       /qlaudified mode | report | csv
qlaudified/                  Python package (standard library only)
eval/                        Fernwick corpus, tasks, runner (Sprints 2-5)
scripts/live.py              isolated live smoke runs
spike/                       Sprint 0 throwaway probes
tests/                       unit, contract, replay, live
```

## License

MIT
