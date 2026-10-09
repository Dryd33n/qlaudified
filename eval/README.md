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

The off condition runs the plugin in Low mode, so Claude sees nothing from it; the post-hoc
condition is those same runs verified offline and needs no runs of its own.
Never run `run.py` without deciding the day's budget first (`--daily-cap`, `--max-runs`).
