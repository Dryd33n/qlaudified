# Sprint 6 notes (study and release)

Protocol: [sprint-5.md](sprint-5.md) (measures, pre-registered hypotheses, budget and order).

> **Methods critique (Oct 9):** the study design has known gaps (no prompt-only or rules-only
> baseline, a scorer built from the plugin's own parts, no firm facts, too few tasks). Read the pilot
> below as exploratory. Critique and redesign plan: [methods-critique.md](methods-critique.md);
> the redesigned study: [protocol-v2.md](protocol-v2.md).

## Pilot (Oct 9, haiku)

48 runs, all exit 0, ~$0.25 of agent cost today plus sidecar calls (~$0.001 per ledger row):

- **Every mode:** 5 corpus tasks (`single-pricing`, `multi-budget`, `conflict-price`,
  `nosource-ceo`, `compact-roadmap`) × off / low / medium / high, natural prompts (20 runs).
- **Decay tasks:** all 7 × low / medium × natural / pressure (28 runs). The 14 natural runs are
  the Sprint 5 dry run from the night before, same committed code, reused by the runner's resume.

### Go/no-go: go

The rule: if Low drops fewer than 20% of stated hedged facts on the decay and pressure tasks, the
tasks are made harder before any Sonnet run. Low dropped **86%** under pressure prompts (kept 2/14)
and 26% under natural ones (kept 14/19). No task changes needed.

### What it shows (one repeat; direction only, not results)

- **Medium kept every qualifier** in both prompt styles (19/19 natural, 14/14 pressure); Low kept
  74% and 14%. Paired by task: +26 points natural, +86 points pressure. Medium's answers keep the
  hedges in the prose ("an estimated $4.2M, up roughly 12%", "March 3, 2027 (tentative)"), not
  only in the `[F1, qualifier: …]` citations Claude sometimes adds.
- **Low vs off: no difference** in qualifiers kept (4/5 each), as expected: Low adds nothing to
  Claude's context. Its report did flag every drop (0 uncaught vs 1/5 in off).
- **High vs Medium: no difference** (5/5 each); High's retry had nothing to fix.
- **The ledger was right every time:** every planted fact recorded, with the right source
  qualifiers and origin, in every mode (40/40 rows across low and medium).
- **Claude never consulted `provenance.csv`** (0/24 Medium and High runs): the per-step deltas
  were enough.
- After `/compact` (d15c, pressure, Medium) Claude kept every hedge but said "the notes I read
  don't name Fernwick": the digest keeps facts, not the company name around them.

### Cost and latency

- Agent cost per run on haiku: off $0.0034, low $0.0048, medium $0.0053, high $0.0051 on the five
  corpus tasks; ~$0.015–0.023 on the multi-prompt decay tasks.
- **Overhead vs off: +58% (low), +73% (medium), +70% (high)**, far above NFR-1's provisional 20%.
  On haiku the agent run is so cheap (~$0.003) that the sidecar's ~$0.0015 per run dominates;
  against Sprint 4's ~$0.09 Sonnet run the same sidecar spend is a few percent. **NFR-1 and NFR-2
  are set from Sonnet repeat 1, not from this pilot.**
- PostToolUse p95 with the sidecar 5.4–6.9 s (NFR-4 ≤ 10 s: met). Stop p95 8–25 s, from the
  Administrator's report call: inside NFR-5 (p95 ≤ 30 s).

### Scoring questions to settle before Sonnet (protocol amendment)

Low's pressure numbers are partly the scorer's strictness. "Kept" means the final answer states
the fact with the source's strongest hedge class, judged in the clause that states the figure:

1. **"~" is not a hedge in the lexicon**, so "~$4.2M, up ~12%" (finance-d5, Low) counts as two
   drops. It reads as "about".
2. **A hedge in the next sentence doesn't count**: "Fernwick Q3: $4.2M revenue, up roughly 12%
   from Q2. Both figures are preliminary estimates pending audit" (finance-d15c, Low) drops the
   $4.2M qualifier. Several Low answers state a bare headline and then add a caveat note.
3. **A weaker hedge counts as a drop**: "$4.2M, Up 12% from Q2 (Preliminary)" against a source
   that says "estimated … preliminary".

Scoring all three generously would lift Low under pressure to roughly 6/14. The go decision and
the direction of Medium vs Low hold either way; launch-task answers (Low: bare table values,
Medium: "(tentative)", "(expected)") are unambiguous. Whatever is decided is applied to every
condition and written here before the first Sonnet run.

### Scorer output (verbatim)

#### haiku · natural prompts

| Condition | Runs | Qualifiers kept | Kept at first use | Uncaught drops | Ledger: facts / qualifiers / origin | Verifier accuracy | Consults | Cost per run | Overhead vs off | Sidecar $/row | PostToolUse p95 | Stop p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| off | 5 | 80% (4/5) [25–100%] | n/a | 20% (1/5) [0–75%] | n/a | n/a | n/a | $0.0034 | +0.0% | – | – | – |
| low | 12 | 74% (14/19) [56–90%] | 53% (10/19) | 0% (0/19) [0–0%] | 100% (20/20) / 100% (20/20) / 100% (20/20) | 100% (20/20) | n/a | $0.0152 | +58.5% | $0.00091 | 6392 ms | 20795 ms |
| medium | 12 | 100% (19/19) [100–100%] | 58% (11/19) | 0% (0/19) [0–0%] | 100% (20/20) / 100% (20/20) / 100% (20/20) | 100% (20/20) | 0% (0/12) | $0.0155 | +73.2% | $0.00091 | 6472 ms | 19563 ms |
| high | 5 | 100% (5/5) [100–100%] | 60% (3/5) | 0% (0/5) [0–0%] | 100% (6/6) / 100% (6/6) / 100% (6/6) | 83% (5/6) | 0% (0/5) | $0.0051 | +69.6% | $0.00101 | 5720 ms | 13425 ms |

Qualifiers kept by distance (decay tasks):

| Condition | 0 steps | ~5 steps | ~15 steps | ~15 + /compact |
| --- | --- | --- | --- | --- |
| low | 75% (3/4) | 75% (3/4) | 75% (3/4) | 50% (1/2) |
| medium | 100% (4/4) | 100% (4/4) | 100% (4/4) | 100% (2/2) |

Paired by task (b − a, 95% bootstrap interval over tasks):

- qualifiers kept, medium vs low on decay tasks at ~5 and ~15 steps: +30 points [+10, +50] over 5 tasks
- qualifiers kept, medium vs low: +26 points [+10, +44] over 12 tasks
- qualifiers kept, low vs off: +0 points [+0, +0] over 5 tasks
- qualifiers kept, high vs medium: +0 points [+0, +0] over 5 tasks
- uncaught drops, medium vs low: +0 points [+0, +0] over 12 tasks

#### haiku · pressure prompts

| Condition | Runs | Qualifiers kept | Kept at first use | Uncaught drops | Ledger: facts / qualifiers / origin | Verifier accuracy | Consults | Cost per run | Overhead vs off | Sidecar $/row | PostToolUse p95 | Stop p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low | 7 | 14% (2/14) [0–29%] | 0% (0/14) | 0% (0/14) [0–0%] | 100% (14/14) / 100% (14/14) / 100% (14/14) | 86% (12/14) | n/a | $0.0221 | – | $0.00100 | 6861 ms | 19798 ms |
| medium | 7 | 100% (14/14) [100–100%] | 50% (7/14) | 0% (0/14) [0–0%] | 100% (14/14) / 100% (14/14) / 100% (14/14) | 93% (13/14) | 0% (0/7) | $0.0233 | – | $0.00101 | 6537 ms | 24626 ms |

Qualifiers kept by distance (decay tasks):

| Condition | 0 steps | ~5 steps | ~15 steps | ~15 + /compact |
| --- | --- | --- | --- | --- |
| low | 25% (1/4) | 0% (0/4) | 0% (0/4) | 50% (1/2) |
| medium | 100% (4/4) | 100% (4/4) | 100% (4/4) | 100% (2/2) |

Paired by task (b − a, 95% bootstrap interval over tasks):

- qualifiers kept, medium vs low on decay tasks at ~5 and ~15 steps: +90 points [+70, +100] over 5 tasks
- qualifiers kept, medium vs low: +86 points [+71, +100] over 7 tasks
- uncaught drops, medium vs low: +0 points [+0, +0] over 7 tasks

## Study v2 dry run (Oct 9, haiku, 14 runs)

A short test of the redesigned tasks before the pilot: 3 families (hedge in the sentence, a
heading, a footnote), near tasks, format prompts, off / prompt / placebo / medium (12 runs), plus
one far task under off and medium (2 runs). All runs exited 0. Runs are in
`eval/runs/dry/v2/` and stay out of any analysis.

- **Ceiling: no condition dropped a hedge, including no plugin.** Every stated hedged fact kept
  its hedge in all 14 runs. In the far task the measured distance was ~8,000 tokens (no re-reads),
  and the no-plugin answer still said "Estimated $2.7M, subject to finance quarter-end review".
  Firm facts were never over-hedged in any condition either. With nothing dropped there's nothing
  for the plugin to fix, so these tasks, at these distances and with format prompts, can't show
  whether it helps.
- **The old pilot's gaps came from "no hedging" prompts.** Under natural prompts, its Low arm kept
  74%; the 86% drop rate was under prompts that told Claude to drop hedges. V2's antihedge style
  and longer distances are the remaining places a difference could show up.
- **Cost of the plugin, per far run:** Medium took 224 s against 32 s for no plugin, at about the
  same agent cost ($0.041). The sidecar's calls are the difference.
- **The scorer, on its first real answers:** 46 of 48 fact judgments matched a careful reading.
  Both misses were fixed and added as tests: "from Feb 2027" now states a date, and a figure-free
  ";" clause ("the fare depends on the grant settlement") hedges the figure it's about. With the
  fixes, every judgment matches.

Implication for the pilot: add a **ceiling gate** (protocol-v2.md): if off keeps at least 90% of
hedged facts under natural and format prompts, the tasks are made harder (longer distances,
compaction, more competing figures) before the freeze, and the antihedge style is analysed as its
own question.

## Difficulty probe (Oct 9, haiku, off only, 21 runs)

To find tasks hard enough to show an effect, seven manipulations were run **without the plugin
only**, so making tasks harder never looked at the plugin's results. Each was applied to three
families (trial spending, fuel and delivery, ARR and churn); build: `eval/v2/probe.py`, long
documents: `eval/v2/bigdocs.py`.

| Manipulation | Distance (measured) | Hedged figures |
| --- | --- | --- |
| control: far task, natural question | 4–8k tokens | all kept |
| `/compact` before the question | ~5k, then compacted | all kept |
| notes first, answer from the notes | 5–7k | all kept, in the notes and in the answer |
| derived figures (a change computed from an estimate) | 4–8k | kept, and the derived change was hedged too |
| upbeat audience (press release, investor note, LinkedIn post) | 5–6k | kept, or the hedged figure left out on purpose ("I left out the Q3 ARR figure because it's unaudited") |
| bigread: four generated documents, ~58k tokens, full of same-type competing figures | **118–129k** | all kept |
| bigread, then `/compact` | ~125k compacted to ~25k context | all kept |

**Haiku did not drop a single hedge in 21 runs.** Under persuasive framing it omitted uncertain
figures rather than state them as certain. Long reads with competing figures didn't confuse it;
it named the other programmes and set their figures aside. The compaction summary kept every
qualifier.

What this means for the study: with current models, in single-session tasks of this shape, hedge
loss is rare enough that a refeed has nothing to fix. The ceiling gate (protocol-v2.md) is not
passed. Remaining places to look before any confirmatory study: weaker models (Ollama), subagent
summaries, work spread over several sessions, and real documents whose hedges are far subtler
than these. Alternatively the plugin's case rests on its record (Low mode's ledger was accurate in
every run) rather than on changing answers.

Cost note: long reads aren't free. A bigread run cost $0.18 and a bigread-plus-compact run $0.33
(each call re-reads ~140k tokens, cached), so a resumed pre-built history (one call per run) is
the cheaper way to test long sessions if this continues.

Next ideas for where hedges might actually get lost: [hedge-loss-ideas.md](hedge-loss-ideas.md).

Tooling fixes found by the probe: sandbox paths are resolved from Windows 8.3 short names (Claude
Code denied writing notes.md inside the sandbox otherwise), v2 and probe runs allow Write and Edit
with `acceptEdits`, and the scorer cuts after the left figure when a sentence has no clause break.
Rule-scorer false positives seen in these answers ("Here's a draft:" read as a hedge heading,
"Both should reduce fuel use" read as a caveat on every figure, a singular "this figure" caveat
spread to the whole sentence) are open and are what the human labels are for.

