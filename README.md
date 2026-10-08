# qlaudified

A Claude Code plugin that tracks where each claim in Claude's answer came from, and whether the source's
qualifiers ("estimated", "may", "tentative") survived the trip.

**Status:** pre-alpha, Sprint 0 (hook spike). Nothing here is usable yet.

- Design and requirements: [docs/design.md](docs/design.md)
- Sprint plan: [docs/sprint-plan.md](docs/sprint-plan.md)
- Testing and dev workflow: [docs/testing.md](docs/testing.md)
- Sprint 0 spike runbook: [spike/README.md](spike/README.md)

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
