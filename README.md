# qlaudified

**A Claude Code plugin that keeps a provenance record of every critical fact Claude reads, and
feeds the sources' qualifiers back so they survive into the final answer.**

![status: pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange)
![python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![dependencies: standard library](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)
![license: MIT](https://img.shields.io/badge/license-MIT-lightgrey)

A source says Q3 revenue was *estimated* at $4.2M, *based on preliminary figures*. Fifteen tool
calls later, Claude's summary says "Q3 revenue was $4.2M." Nothing in it is invented, yet the claim
is now wrong. qlaudified is a Claude Code plugin intends to catch and prevent that loss.

- **The problem:** when work is handed over between sessions, Claude turns "may have reduced
  fatigue by about 30%" into "reduces fatigue by 36%". Without the plugin, 13 of 14 hedged
  findings were stated as firm once Claude was handed a finished report.
- **The result:** in a pre-registered, placebo-controlled comparison, the plugin raised hedges
  kept from **24% to 88%**, and the qualifiers it feeds back are what do it.
- **The catch:** it also hedges some firm findings (29% vs 6% without it), so it did not meet the
  pre-registered bar. Tested on Haiku only, on synthetic sources.

## Introduction

### The problem

Research work in Claude Code rarely ends where the sources were read. Findings get parsed, ranked
and written into a report, and a later session is asked to turn that report into a slide. Each
step keeps the number and can drop the qualifier. Every study of yoga in this example said "may
have reduced", "possibly" or "appeared to". The slide Claude made from the report (Haiku, no
plugin) said:

> **Yoga:** Ranked #1 of 20 on effect per $100. Costs $40/patient and reduces fatigue by 36%.

Nothing is invented, yet the claim is now stronger than the evidence.

### The solution

qlaudified records each critical fact as Claude reads it (what it says, where it came from, how
the source qualified it) and feeds that record back into Claude's loop, including into later
sessions of the same project. With it on, a session handed the same kind of report, which opened
no source file itself, wrote:

> **Acupuncture (rank 2 of 20):** Reduces chronic pain by about 33% at $60 per patient…
> *Footnote:* … Source abstracts describe both effects with hedged language ("appeared to,"
> "may have"), so treat the percentages as estimates.

## Results

### Hypothesis

Feeding the provenance record back keeps sources' qualifiers in the final answer where Claude
would otherwise lose them, without hedging what the sources stated firmly, and the qualifiers in
the record are what do it, not merely reminding Claude of the facts.

### Finding 1: where hedges get lost without the plugin

Haiku, no plugin, Oct 9–21, 2026, counted by hand:

| Workflow | Hedged findings lost |
| --- | --- |
| Answering from sources still in context (summaries, notes, `/compact`, ~120k tokens of competing figures; 21 runs) | **none** |
| A fresh session answers from a pipeline's output, sources on disk, asked how strong the evidence is | **0 of 6** (it reopens the sources) |
| The same, asked for a board slide, leaflet or reply | **5 of 15** |
| The user **pastes the finished report**, or asks to **turn it into** a slide or reply | **13 of 14** |

Loss is not about distance or context length. Claude keeps hedges while the source is in view and
checks the source when asked about evidence. It loses them when handed a firm-looking document to
transform. That handoff became the evaluation task.

### Finding 2: the plugin in the handoff

An earlier session read the abstracts with the plugin on; a fresh session was then handed the firm
report and asked for a board slide or a reply to a clinic manager. Two pre-registered comparisons
(Oct 21–22, 2026); the latest covers three task families, one held out from tuning, with 24 runs per
arm on Haiku, labelled blind by hand
([protocol and full results](eval/README.md#pre-registered-comparison-2-oct-21-2026)).

| Arm | Hedged findings kept (of stated) | Firm findings wrongly hedged |
| --- | --- | --- |
| Off: no plugin | 24% (10/42) | 6% (3/48) |
| Prompt: one instruction to keep the sources' qualifiers | 33% (13/39) | 8% (3/39) |
| Placebo: the plugin's facts with their qualifiers masked | 44% (22/50) | 24% (12/50) |
| **Medium: the plugin** | **88% (44/50)** | **29% (15/52)** |

- **The qualifiers are what keep the hedges.** Medium beat placebo in 11 of the 12 paired cells
  where they differed (sign test, p = 0.003), and an instruction alone barely helped. The first
  comparison, on two families, showed the same (92% kept, 8 of 8 cells). On the held-out family,
  Medium kept 71% against 40% for placebo and 23% off.
- **It also over-hedges, so the pre-registered rule was not met.** Firm findings were hedged 23
  points more often than with the plugin off; the limit was 15. Each case is one blanket sentence
  over all the figures, almost always in a reply: "several of the studies report estimates rather
  than precise results, so treat them as a guide". Carrying the firm facts as well, the fix tested
  in comparison 2, made answers state more firm findings plainly (25 vs 15 on the same two
  families) but barely reduced these blanket caveats (4 of 16 runs, from 5).

**How the comparisons were run.** Each design and decision rule was committed before its runs.
The placebo arm separates "the right information" from "more information". Answers were exported
under random IDs and labelled by hand before unblinding; labels, unblinding keys and scripts are
in `eval/handoff/labels/`. Mistakes found along the way are reported, not fixed silently
(a truncated export, a scorer bug, misattributed quotes).

### Caveats

- Haiku only, on synthetic studies whose hedges are plain words. Stronger models may lose fewer
  hedges on their own.
- 24 runs per arm: enough to see a pattern, not to measure its size precisely. The held-out family
  alone (8 runs per arm) is too small to test on its own.
- One labeller. In comparison 1, six labels were corrected after unblinding, because the blind
  export had cut long answers; in comparison 2 one labelling rule was made explicit partway,
  before unblinding. Answers from plugin arms sometimes cite ledger IDs, which the blinding could
  not hide.
- The plugin's sidecar calls are billed separately from the session costs reported.

## How it works

**A sidecar agent.** On each tool call, a hook extracts the facts Claude just read: sentences or
lines with a number, a date or a hedge word from a lexicon. When a step has new facts, uses of
earlier ones or claims of Claude's own, a second agent, the **Provenance Administrator** (Haiku via
`claude -p --safe-mode`), judges them: is the fact critical, what is its origin, which qualifiers
did the source attach that the lexicon missed, and how did it shape the answer. It runs beside
Claude, not inside its context.

**A rolling CSV that is fed back.** The record is a read-only `provenance.csv` per session,
rewritten after every step and closed by a provenance report at the end of each answer. In Medium
and High mode it goes back into Claude's loop as plain factual lines, never instructions: where the
CSV is at session start, each step's new facts after the step, a digest after `/compact`, and,
when a prompt or a file names something an earlier session recorded, those earlier facts.

```
 Claude reads a file, page or command output
        │
        ▼
 PostToolUse hook ── facts and source logged ── Provenance Administrator judges them
        │
        ▼
 provenance.csv rewritten ──▶ Medium/High: new and matching earlier facts go back to Claude
        │
        ▼
 Stop hook ── checks the answer's claims against the record, writes the report
```

A row of `provenance.csv`, from a live run:

| fact_id | claim | source | source_qualifiers | first_use_qualifiers | operational_impact |
| --- | --- | --- | --- | --- | --- |
| F1 | Q3 revenue is estimated at $4.2M, based on preliminary figures. | q3-finance.md L3 | estimated; preliminary | estimated | conclusion: Final answer's $4.2M figure stands as an estimate… |

And how a fact goes back to Claude:

```
[F29 abstracts/A010.md L10] Pharmacist medication review may have reduced adverse drug events by about 41%…; source says: may, about
```

| Mode | Records the provenance | Feeds it back to Claude | Retries a dropped qualifier |
| --- | :---: | :---: | :---: |
| Low | ✓ | | |
| **Medium** (default) | ✓ | ✓ | |
| High | ✓ | ✓ | once per answer |

## Plugin installation

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
sidecar uses your existing Claude Code login (Haiku by default) or a local Ollama model, and only
it sees excerpts; no passages are stored. Overhead on Windows 11: 364 ms per tool call (p95) without
a sidecar call, 5–7 s with one; the sidecar costs about $0.001 per recorded fact
([sprint-5.md](docs/findings/sprint-5.md)).

## Open questions

- **Does the problem exist on stronger models?** Everything above is Haiku. If Sonnet or Opus
  rarely lose hedges in the handoff, the plugin has less to fix. This is the cheapest and most
  important next test.
- **Can the over-hedging be reduced?** Carrying firm facts did not stop the blanket caveat. A
  per-intervention summary ("Yoga: 6 sources, all hedged · Pharmacist review: 6 sources, none
  hedged") might; some of it may simply be how Claude writes replies.
- **The report cannot see the handoff case yet.** It checks an answer only against facts read in
  the current session, so a firm report's figures look supported. Adding carried facts to the
  session's ledger would let it flag the loss.
- **What if the sources were never read through Claude's tools?** When a script Claude wrote
  parses the sources, the plugin never sees the hedges and has nothing to carry.
- **Implied uncertainty is invisible.** The rules need a number, a date or a hedge word, so a
  12-person pilot or a confidence interval crossing 1 is never flagged.
- **Is the cost worth it?** On Haiku the plugin adds 58–73% to a task's cost, because a Haiku run
  is so cheap; that has not been measured on larger models.

## Documentation

[Design and requirements](docs/design.md) · [Evaluation method and results](eval/README.md) ·
[Sprint plan](docs/sprint-plan.md) · [Testing and dev workflow](docs/testing.md) · Sprint findings
[0](docs/findings/sprint-0.md) · [1](docs/findings/sprint-1.md) · [2](docs/findings/sprint-2.md) ·
[3](docs/findings/sprint-3.md) · [4](docs/findings/sprint-4.md) · [5](docs/findings/sprint-5.md) ·
[6](docs/findings/sprint-6.md)

## Development

The core is standard-library Python, so the hooks run on plain system Python with no virtualenv.
Hooks never fail a session: every error is logged and the hook exits 0. 261 tests cover unit
behaviour, the hook contract (recorded payloads piped in exactly as Claude Code sends them) and
replays of recorded sessions; a separate live layer runs real `claude -p` sessions.

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
eval/                        handoff tasks, runner, scorer, labels
scripts/                     live smoke runs and latency benchmarks
spike/                       Sprint 0 throwaway probes
tests/                       unit, contract, replay, live
```

## License

MIT
