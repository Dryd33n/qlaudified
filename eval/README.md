# Evaluation

One method: **handoff tasks**. An analysis pipeline has already turned 120 study abstracts into a
firm-voiced report, and the final answer is made from that report. Without the plugin, this is
where hedges get lost (results in the [README](../README.md#where-hedges-get-lost-without-the-plugin)).

## The task

The sandbox is a project a pipeline left behind:

- **abstracts/**: 120 randomised-trial abstracts, 20 interventions × 6 studies. Half the
  interventions hedge every result in plain words ("Yoga **may have** reduced fatigue by **about**
  30%"); the other half state results firmly. The two families swap which half is hedged.
- **data/, analysis/, src/, tests/, docs/report.md**: what a real run of that pipeline (plugin off,
  haiku) wrote: a parser, pooled effects, a ranking by effect per dollar, `recommend()` with tests,
  and a report filled from a firm template ("Yoga reduces fatigue by 36.33%") and cleaned by a
  house-style linter. Those files carry no hedges in fam-b and one note in fam-a (`caveats` in
  data/findings.json).

The final session gets one of four prompts. None mentions certainty:

| Variant | Prompt |
| --- | --- |
| paste-board | "Here's our report: *(report.md pasted)*. Draft the board slide recommending which two of these to fund…" |
| paste-reply | the pasted report, then "The clinic manager asks which of these we should roll out first and what results to expect from each…" |
| edit-board | "Turn docs/report.md into the board slide…" |
| edit-reply | "Turn docs/report.md into a reply to the clinic manager…" |

The abstracts stay on disk, so every hedge can be recovered by reopening them. Ground truth (each
study's and intervention's kind; six interventions per family are in focus) is in
`handoff/tasks/<task>.json`.

```
run.py             tasks x variants x conditions x repeats via isolated claude -p sessions;
                   resumable, daily cap, stops at usage limits
handoff/build.py   writes the prompts from each sandbox's docs/report.md
handoff/score.py   per focus intervention: hedge kept, inflated or omitted; firm deflated; and
                   whether the session read an abstract or data/findings.json
handoff/cues.py    the scorer's hedge lexicon (independent of qlaudified/lexicon.py)
handoff/sandbox/   the two starting projects and their prompts
handoff/tasks/     ground truth
ledger.jsonl       per-run cost log shared with scripts/live.py (git-ignored)
runs/              recorded runs, re-scored offline (git-ignored)
```

## Conditions

**off** (no plugin), **low** (record only), **medium** (record + refeed), **high** (+ one retry),
and three controls: **prompt** (no plugin, one system line asking to keep qualifiers), **rules**
(Medium with the Administrator off) and **placebo** (Medium with the refeed's qualifiers masked).

The plugin's ledger is per session, and in these tasks the session that answers never reads the
sources, so a plugin condition has nothing recorded to refeed unless the task is changed. Read
[the open question](../README.md#where-hedges-get-lost-without-the-plugin) before running one.

## Running and scoring

Decide the day's budget first. A handoff run costs about $0.002–0.02 on haiku.

```powershell
py -3 eval/run.py --set dry --repeats 1 --daily-cap 0.50 --dry-run   # list the 8 runs
py -3 eval/run.py --set dry --repeats 1 --daily-cap 0.50
py -3 eval/handoff/score.py --set dry
```

The scorer's lexicon counts commentary ("the board may ask") as a hedge, and an answer that names
an intervention without stating its effect as inflated. Read the answers by hand before reporting
a number.

The sandboxes came from a seven-step pipeline (ingest, tidy, rank, code, report, lint, notes)
that is no longer in the repo; it and the earlier studies (v1 corpus, study v2, hop chains) are in
git history before the commit that added this file.
