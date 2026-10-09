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
