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

## Pre-registered comparison (Oct 21, 2026)

Written before any plugin-condition handoff run. Code frozen at commit `4651ca3` (carry-over,
runner, scorer); nothing in `qlaudified/` or `eval/` changes until the comparison is scored,
except to fix a crash, which would be reported.

**Question.** When the user hands over a firm report built from hedged sources, does the
plugin's carry-over (RFD-5) keep the hedges in the answer, and is it the qualifiers it carries
back that do it?

**Arms.** off (baseline) · prompt (no plugin, one system line asking to keep qualifiers) ·
placebo (the plugin carrying the same lines with qualifiers masked) · medium (the plugin).
Primary contrast: **medium vs placebo**. Secondary: medium vs off, prompt vs off.

**Design.** 2 families × 4 variants = 8 cells, 2 repeats, haiku: 16 runs per arm, paired by
cell and repeat. The off runs of Oct 21 are off's repeat 1. Every plugin arm starts from the
same frozen earlier ledger per family (the prep variant, medium, one run per family).

- *Manipulation checks.* Before the comparison: the frozen ledger holds the hedged focus
  findings with their qualifiers. After each plugin run: whether anything was carried
  (`carried.json` in the run's store). A run where the carry-over did not fire is kept and
  counted against the plugin.

**Scoring.** The unit is a hedged focus finding the answer states. Answers are exported with
random IDs and no condition, labelled by hand (kept / lost / not stated), then unblinded. Firm
focus findings are labelled too (plain / deflated) as a guard against hedging everything.
Primary rate: kept among stated. Sensitivity: "not stated" counted as lost. The lexical scorer
(`handoff/score.py`) is reported alongside, with its disagreements.

**Decision rule.** A pattern is present if all three hold:

1. In the 16 paired cells, medium keeps a larger share of hedges than placebo in at least 12 of
   the cells that differ (one-sided sign test, p < 0.05);
2. the pooled kept rate is at least 30 points higher for medium than for placebo;
3. firm findings deflated under medium are no more than 15 points above off.

If 1 and 2 clearly fail, there is no pattern. If the result is borderline, one more repeat
(r3) of all four arms, declared now, and no further extension.

**Limits.** Haiku only; synthetic sources with plain hedges; the carry-over matching was
designed while looking at these two families (no held-out family); one prep session per family;
one labeller.

### Result (Oct 21, 2026)

64 runs (16 per arm), all valid; blind hand labels. The carry-over fired in every plugin run
(16/16 medium, 16/16 placebo), and only 1 of 16 medium runs read an abstract, so the hedges
medium kept came from the carried facts. (First reported as "no medium run"; the scorer missed
reads after `cd abstracts`, fixed since.)

The table below uses the blind labels. They undercount hedges in all arms; see **Correction**.

| Arm | Hedged kept, of stated | Kept, of all 48 hedged (sensitivity) | Firm deflated, of stated |
| --- | --- | --- | --- |
| off | 24% (7/29; 95% CI 12–42) | 15% (7/48) | 0% (0/33) |
| prompt | 34% (10/29; 20–53) | 21% (10/48) | 0% (0/28) |
| placebo | 29% (10/35; 16–45) | 21% (10/48) | 0% (0/36) |
| **medium** | **76% (28/37; 60–87)** | **58% (28/48)** | **30% (9/30; 17–48)** |

Paired cells, medium vs placebo: medium higher in 8, lower in 0, tied or undefined in 8 (sign
test p = 0.004); counting unstated findings as lost, 9 vs 1 (p = 0.011). Prompt vs off and
placebo vs off: no difference (2–0 and 3–3).

**Against the decision rule:**

1. Sign test: passes (8 of 8 differing cells, p = 0.004). As written, the rule also asked for
   "at least 12 of the cells that differ", a count that assumed all 16 would differ; only 8 did,
   so that literal threshold cannot be met. Reported as written.
2. Pooled difference: passes, +47 points (+37 counting unstated findings as lost).
3. Firm deflation: **fails**, 30% under medium vs 0% under off (limit +15). All 9 come from 3
   medium reply answers that told the reader every figure was an estimate because the sources
   hedge, applying the hedged studies' caveat to the firm ones too.

**Verdict: the pre-registered pattern is not established**, because criterion 3 fails clearly
(not borderline, so no r3). What the data do show: the carry-over keeps hedges (76% vs 24–34%
in every other arm), and it is the qualifiers that do it (placebo carries the same lines without
them and does no better than off); the instruction alone does not. The cost is over-hedging:
in 3 of 16 medium runs the carried caveats spread to firm findings.

**Correction (after unblinding, not blind).** The blind export cut each intervention's text at
330 characters, which hid hedge notes in 26 answers. Reading those hidden lines with the same
rules changed six labels (`labels/labels-corrected.txt`); four were blanket caveats ("the study
abstracts use hedged language, so the figures are estimates"):

| Arm | Hedged kept, of stated | Kept, of all 48 | Firm deflated, of stated |
| --- | --- | --- | --- |
| off | 24% (7/29) | 15% (7/48) | 0% (0/33) |
| prompt | 45% (13/29) | 27% (13/48) | 11% (3/28) |
| placebo | 40% (14/35) | 29% (14/48) | 17% (6/36) |
| **medium** | **92% (37/40)** | **77% (37/48)** | **50% (15/30)** |

Medium vs placebo in paired cells: still 8 higher, 0 lower (p = 0.004); 10 vs 1 counting unstated
findings as lost. The verdict does not change: criterion 3 fails by more.

**Why firm findings were hedged.** Every deflated firm finding comes from one blanket sentence
over all the figures ("The figures above should be read as estimates"); no answer hedged a
specific firm finding. Of the 27 answers that mention the sources' hedging:

| | Blanket caveat | Itemised (names the unhedged ones) | Flags hedged ones only |
| --- | --- | --- | --- |
| Reply to the clinic manager | 8 | 6 | 4 |
| Board slide | 0 | 2 | 7 |
| Had evidence that some findings were firm | 4 | 6 | 3 |
| Had no such evidence | 4 | 2 | 8 |

The reply genre ("what results to expect from each") draws a single caution about the figures;
a slide line flags its own item or nothing. And Claude itemises when it can see which findings
are firm (fam-a's full `findings.json`, whose `caveats` field is empty for firm records, or the
abstracts). The carry-over sends only qualified facts, so it says which sources hedge, never
which do not: 4 of medium's 5 blanket caveats came with no evidence of firm findings. The next
change to test: carry the matched firm facts too, marked as stated plainly in the source.

Scorer agreement: poor. The lexical scorer reports 0–58% kept and 33–75% firm deflated across
arms, mostly from commentary words; only the hand labels are used above. Cost: $0.29 for the 55
new runs as logged; the plugin's sidecar calls are billed separately and not included. Limits as
pre-registered, plus: answers from plugin arms sometimes cite ledger IDs (`[F12]`), which the
blinding could not hide.

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
