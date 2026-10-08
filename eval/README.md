# Evaluation

Synthetic "Fernwick Co." corpus plus a mode ablation (design.md, "Evaluation plan").

```
corpus/      docs, code repo and saved web pages with planted, hedged facts   (Sprint 2 seed, Sprint 4 full)
tasks/       one TOML per task: prompt, expected facts, source spans, qualifiers
run.py       tasks x {off, medium, high} x 2 repeats via claude -p; resumable (Sprint 4)
score.py     qualifier preservation, attribution P/R, verifier accuracy, cost, latency (Sprint 4)
ledger.jsonl per-run cost log shared with scripts/live.py (git-ignored)
runs/        recorded runs, re-scored offline (git-ignored)
```

The post-hoc condition is the Off runs verified offline; it needs no live runs.
Never run `run.py` without deciding the day's budget first.
