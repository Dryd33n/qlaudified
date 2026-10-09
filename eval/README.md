# Evaluation

Synthetic "Fernwick Co." corpus plus a mode ablation (design.md, "Evaluation plan"). The study
protocol, hypotheses and budget are in [docs/findings/sprint-5.md](../docs/findings/sprint-5.md).

```
tasks/       one TOML per task: expected facts, source spans, qualifiers, kept/dropped claims
             (20 tasks, 4 per type; sandboxes and prompts in tests/sandbox/<task>/:
             prompt.txt is natural, prompt-pressure.txt is the same question under a constraint)
run.py       tasks x {natural, pressure} x {off, medium, high} x repeats via claude -p;
             resumable, daily cap, stops at usage limits
score.py     uncaught drops (headline), qualifiers kept, drops flagged, verifier accuracy,
             attribution P/R, cost and overhead, latency; bootstrap intervals and paired
             comparisons by task
ledger.jsonl per-run cost log shared with scripts/live.py (git-ignored)
runs/        recorded runs, re-scored offline (git-ignored)
```

Conditions (design revision 2): **off** (no plugin), **low** (record only: the sidecar builds the
ledger and report, nothing reaches Claude), **medium** (record + refeed), **high** (+ one retry).
Tasks: the 20 corpus tasks plus 7 decay tasks (`decay-*`: the question 0, ~5 or ~15 tool calls
after the hedged fact is read, one variant compacted). One repeat is 216 runs. Never run `run.py`
without deciding the day's budget first (`--daily-cap`, `--max-runs`).

## Study v2 (protocol: docs/findings/protocol-v2.md)

The corpus above (v1) is frozen as exploratory after the methods critique. Study v2 lives in `v2/`:

```
v2/families/   16 task families in TOML: source documents, distractors, facts (value, unit,
               hedged or firm, the source's cue)
v2/build.py    builds v2/sandbox/ and v2/tasks/ (near and far tasks; natural, format and
               antihedge prompts); --check compares with MANIFEST.json (the frozen task set)
v2/calib.py    per-fact calibration: kept, inflated, deflated or omitted; format compliance
v2/cues.py     hedge cues, written independently of the plugin's lexicon
v2/figures.py  money, percentages, counts and dates in text
v2/transcript.py  distance in tokens and re-reads from each run's transcript
v2/score.py    report per condition and prompt style; primary and Holm-adjusted contrasts
v2/stats.py    family-level sign-flip test, bootstrap, Holm, McNemar, equivalence, power
v2/judge.py    condition-blind LLM judge (uses plan usage)
v2/labels.py   blind labelling sheet and Cohen's kappa against each scorer
v2/power.py    simulated power from the pilot
```

Nothing in `v2/` imports the plugin (a unit test checks). Runs:

```
py -3 eval/run.py --suite v2 --set pilot --tasks <ids> --variants natural,format                   --conditions off,prompt,placebo,medium --repeats 1 --daily-cap <usd>
py -3 eval/v2/score.py --set pilot --out pilot.md --rows pilot-rows.csv
```

v2 conditions: off, **prompt** (one system line asking to keep qualifiers), **rules** (Medium with
no Administrator), **placebo** (Medium with qualifiers masked out of the refeed), medium; low and
high are secondary. One full repeat is 480 runs (32 tasks × 3 styles × 5 conditions).

