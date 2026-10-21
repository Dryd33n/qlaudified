# qlaudified

**Provenance for Claude Code research work: every critical fact, where it came from, and whether
its qualifiers survived.**

![status: pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange)
![python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![dependencies: standard library](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)
![license: MIT](https://img.shields.io/badge/license-MIT-lightgrey)

A source says Q3 revenue was *estimated* at $4.2M, *based on preliminary figures*. Fifteen tool
calls later, Claude's summary says "Q3 revenue was $4.2M." Nothing in it is invented, yet the claim
is now wrong. qlaudified is a Claude Code plugin that catches that decay.

As Claude works, a sidecar agent, the **Provenance Administrator**, records each critical fact:
what it says, where it came from, how the source qualified it, whether that qualifier survived each
use, and how the fact shaped the answer. The record is a rolling, read-only `provenance.csv`,
closed by a provenance report at the end of every answer. In Medium and High mode the record is
also fed back into Claude's loop, so qualifiers survive long tasks.

## Where hedges get lost without the plugin

Haiku, no plugin, Oct 9–21, 2026. Every number is counted by hand from the answers; runs are few
(2 to 21 per row), so read them as rates to confirm, not measurements.

| Workflow | Hedged findings lost |
| --- | --- |
| Answering from sources still in context: summaries, notes, `/compact`, ~120k tokens of competing figures (21 runs) | **none** |
| Rewriting the same findings through a chain of formats, each step a fresh session (CSV, one-liners, slides, FAQ…) | 1 of 12 at 10 steps; 2 of 6 at 20 steps, by drift ("may include symptoms" became "the study found treatment works") |
| Turning hedged figures into data: parsing to a numeric field, pooling, ranking, code constants, a report filled from a firm template | ingest strips the hedge in 6 of 8 runs; ranking and code lose all of them in 8 of 8; the report keeps them in 1 of 8 |
| A fresh session answers from those files, sources still on disk, asked **how strong the evidence is** | **0 of 6** (it reopens the sources every time) |
| The same, asked for a board slide, patient leaflet or a reply to a manager | **5 of 15** (2 of 6 runs) |
| The user **pastes the report**, or asks to **turn it into** a slide or reply | **13 of 14** (6 of 8 runs never opened a source) |

So the loss is not about distance or context length. Claude keeps hedges while the source is in
view and goes back to the source when the question is about evidence. It loses them when the
work hands it a finished, firm-looking document and asks for a transformation of it: then it
critiques what it can see ("the report says 'pooled', but the code takes an unweighted mean")
and never asks whether the findings underneath were hedged. Example, from a pasted report:

> **Yoga:** Ranked #1 of 20 on effect per $100. Costs $40/patient and reduces fatigue by 36%.

Every yoga abstract said "may have", "possibly" or "appeared to". The handoff tasks are the
evaluation method (`eval/README.md`).

**With the plugin** (pre-registered, 64 runs, Oct 21): the ledger was per session, so it had
nothing to refeed in this workflow; it now carries qualified facts from earlier sessions (RFD-5).
In the handoff tasks Medium kept **92%** of hedges against 24% off, 45% with an instruction to keep
qualifiers, and 40% with a placebo that carries the same facts without their qualifiers. But it
also hedged half the firm findings (50% vs 0% off), always through one blanket caveat in a reply
("the figures above should be read as estimates"), because the plugin says which sources hedge
and never which do not. So the pre-registered rule is not met. Numbers use labels corrected
after unblinding; [details](eval/README.md#result-oct-21-2026).

## How it works

```
 Claude reads a file, page or command output
        │
        ▼
 PostToolUse hook ── rules extract facts (numbers, dates, qualifiers) and log the source
        │
        ├─ step meets the threshold? ──▶ Provenance Administrator (haiku via claude -p --safe-mode)
        │                                 critical or not · origin · extra qualifiers · impact
        ▼
 provenance.csv rewritten (read-only)
        │
        ├─ Low:    nothing reaches Claude
        └─ Medium: new facts go back to Claude as plain lines, with their qualifiers
        ▼
 Stop hook ── checks the answer's claims against the record, writes the report;
              High asks Claude to revise once if a qualifier was dropped
```

A row of `provenance.csv`, from a live run:

| fact_id | claim | source | source_qualifiers | first_use_qualifiers | operational_impact |
| --- | --- | --- | --- | --- | --- |
| F1 | Q3 revenue is estimated at $4.2M, based on preliminary figures. | q3-finance.md L3 | estimated; preliminary | estimated | conclusion: Final answer's $4.2M figure stands as an estimate… |

And the line you see after each answer:

```
qlaudified: 3 claims checked · 1 qualifier dropped (pending) · 1 unresolved · 1 supported · /qlaudified report
```

## Modes

| Mode | Records the provenance | Feeds it back to Claude | Retries a dropped qualifier |
| --- | :---: | :---: | :---: |
| Low | ✓ | | |
| **Medium** (default) | ✓ | ✓ | |
| High | ✓ | ✓ | once per answer |

## Quick start

Requires Python 3.11+, and Git for Windows on Windows. From a project folder (not this repo's own
working copy), load the plugin for a session:

```sh
claude --plugin-dir /path/to/qlaudified
```

| Command | What it does |
| --- | --- |
| `/qlaudified mode [low\|medium\|high]` | Show or set the mode for the project; `--session` for this session only |
| `/qlaudified report` | The last answer's claim-by-claim report; `--deep` adds one LLM call for claims the rules couldn't settle |
| `/qlaudified csv` | Open this session's `provenance.csv`; `--path` prints its location |
| `/qlaudified nli install` | Download the optional NLI verifier (`pip install "qlaudified[nli]"`) |

Everything is stored under `.claude/.qlaudified/` in your project, which ignores itself in git. The
sidecar uses your existing Claude Code login (haiku by default) or a local Ollama model, and only
it sees excerpts. No passages are stored.

## Performance and cost

Measured on Windows 11 under ordinary background load ([sprint-5.md](docs/findings/sprint-5.md)):

| | Target | Measured |
| --- | --- | --- |
| Hook overhead per tool call, no sidecar call (p95) | ≤ 400 ms | 364 ms (117 ms of it is shell and Python startup) |
| Tool call with a sidecar call (p95) | ≤ 10 s | 5.4–6.9 s |
| Report at the end of each answer (p95) | ≤ 30 s | 8–25 s |
| Sidecar cost (haiku) | as low as possible | ~$0.001 per recorded fact, ~$0.02 for a 20-step task |
| Cost overhead vs no plugin | set from the Sonnet study | on haiku, +58% to +73%, because a haiku run itself costs only ~$0.003 |

## Progress

| Sprint | Goal | Status |
| --- | --- | --- |
| 0 | Prove the hooks behave as the design assumes | ✅ [findings](docs/findings/sprint-0.md) |
| 1 | Plugin skeleton, mode command, capture into the store | ✅ [results](docs/findings/sprint-1.md) |
| 2 | Medium mode end to end | ✅ [results](docs/findings/sprint-2.md) |
| 3 | Web sources, NLI and LLM tiers | ✅ [results](docs/findings/sprint-3.md) |
| 4 | High mode and the eval harness | ✅ [results](docs/findings/sprint-4.md) |
| 5 | The Provenance Administrator (design revision 2) | ✅ [results](docs/findings/sprint-5.md) |
| 6 | Study, README, v1.0.0 (target Nov 22, 2026) | 🔄 found where hedges get lost (above); plugin test next |

Sprints 0–4 built design revision 1 (rule-based capture and verification). On Oct 8 the design
returned to its original idea: the sidecar's provenance record is the core, and feeding it back
is the hypothesis under test.

## Documentation

- [Design and requirements](docs/design.md)
- [Sprint plan](docs/sprint-plan.md)
- [Evaluation method](eval/README.md)
- [Testing and dev workflow](docs/testing.md)
- Sprint findings: [0](docs/findings/sprint-0.md) · [1](docs/findings/sprint-1.md) ·
  [2](docs/findings/sprint-2.md) · [3](docs/findings/sprint-3.md) · [4](docs/findings/sprint-4.md) ·
  [5](docs/findings/sprint-5.md) · [6](docs/findings/sprint-6.md) · [spike runbook](spike/README.md)

## Development

```powershell
py -3 -m pip install -e ".[dev]"     # Windows; use python3 on macOS
py -3 -m pytest -q -m "not live"     # free test layers: unit, hook contract, replay
```

```
.claude-plugin/plugin.json   plugin manifest
hooks/hooks.json             hook registrations: py -3 if present, else python3
hooks/run.py                 single hook entry point: run.py <event>
hooks/cli.py, launch.sh      /qlaudified entry point and Python picker
skills/qlaudified/SKILL.md   /qlaudified mode | report | csv | nli
qlaudified/                  Python package (standard library only)
eval/                        handoff tasks, runner, scorer
scripts/live.py              isolated live smoke runs
scripts/bench_capture.py     end-to-end hook latency (NFR-3)
scripts/bench_sidecar.py     sidecar step cost and latency (NFR-4)
spike/                       Sprint 0 throwaway probes
tests/                       unit, contract, replay, live
```

## License

MIT
