# qlaudified Study: Methods Critique

Oct 9, 2026 · Dryden

> **Status: saved to be worked on later.** The critique below is as written. After it come notes
> from checking it against the repo, a proposed plan, and the decisions still open. Nothing here
> has been implemented yet. The haiku repeat-1 batch running on Oct 9 uses the old design and
> counts as exploratory data only.

## Verdict

As designed, the study cannot support its headline claim. The pilot shows that Medium's answers contain the source's hedge words more often than Low's. It does not show that the plugin makes answers more faithful, that the ledger or sidecar is responsible, or that the effect survives any task a sceptical reader didn't write. Each gap below is fixable before the Sonnet runs, and fixing them costs less than the runs themselves.

Scope: this reviews `docs/findings/sprint-5.md` (protocol), `sprint-6.md` (pilot), `docs/evaluation.md`, `eval/score.py` and `eval/tasks/` at commit `58dc342`. It critiques methods only; the engineering is not in question.

| # | Problem | Severity | Why |
| --- | --- | --- | --- |
| 1 | No prompt-only or rules-only baseline | Fatal | The effect could come from any reminder, not from the ledger |
| 2 | Pressure prompts instruct Claude to drop hedges | Fatal | "Kept" partly measures disobeying the user |
| 3 | Scorer reuses the plugin's own lexicon and verifier | Severe | Plugin and judge share the same blind spots |
| 4 | No unhedged facts, so over-hedging is invisible | Severe | A plugin that hedges everything scores 100% |
| 5 | Tasks are easy and the target fact is the only salient one | Severe | Decay at "15 steps" is 15 one-line distractors |
| 6 | 5–7 tasks, one repeat, intervals at the ceiling | Severe | Bootstrap over so few tasks is not an inference |
| 7 | Medium differs from Low in several ways at once | Major | Which component works is unidentifiable |
| 8 | Protocol changed the day of the pilot; scoring rules still open | Major | Pre-registration is only partly real |
| 9 | Cost overhead mis-framed; Stop latency unmeasured as harm | Moderate | The cost case is weaker than it reads |
| 10 | One vendor, one harness, author-written corpus | Moderate | Limits the claim, not the study |

## Construct validity: what "qualifier kept" measures

The primary metric is "the final answer contains the source's strongest hedge class near the figure." That is a lexical proxy for faithfulness, and it fails in both directions.

- **It rewards hedge words, not correct certainty.** An answer that puts "estimated" on every number scores perfectly. Nothing in the corpus checks the opposite error (see the harms section), so the metric is one-sided by construction.
- **It conflates faithfulness with disobedience.** `decay-finance-d5`'s pressure prompt says "single punchy headline, no hedging." Medium keeping "estimated" there is scored as a win. It may be the right behavior, but it is a different construct: the plugin overriding an explicit user instruction. Right now you cannot tell "Medium is more faithful" from "Medium's injected text outweighs the user."
- **Omission is not counted.** The denominator is hedged facts *stated*. An answer that silently omits the hedged figure has no drop. If one condition omits more, its keep rate is inflated. Report stated-rate per condition alongside keep-rate.
- **"Strongest hedge class" is arbitrary.** Your own pilot notes show "~", next-sentence caveats, and weaker hedges ("preliminary" for "estimated … preliminary") all scored as drops. A human reader would call most of those faithful. The metric's threshold is doing much of the work in the Low-under-pressure number (14% vs a generous ~43%).
- **Hedge presence is not meaning.** "Revenue may be $4.2M" and "revenue is estimated at $4.2M" both pass, but "revenue was $4.2M (some say estimated)" also passes. Clause matching helps; it doesn't fix this.

**Fix.** Define the construct as calibration, not hedge presence: for each stated fact, is the expressed certainty *equal to* the source's (kept), *stronger* (inflated), or *weaker* (deflated)? Score all three. Report omission separately. Treat instruction compliance as its own outcome on any prompt that constrains style.

## Conditions and baselines

The comparison that matters is not Medium vs Low; it is Medium vs the cheapest thing that could produce the same effect. Without that, H1 tests "does adding hedge words to context make the model repeat hedge words," which nobody doubts.

**Missing conditions**

- **Prompt-only.** Off plus one system line: "When you state a figure from a source, keep the source's qualifiers." Free, zero latency. If it matches Medium, the plugin's refeed adds nothing.
- **Rules-only refeed.** Revision 1's deterministic deltas, no Administrator. Your rules already filled the ledger at 100%; the sidecar may contribute only cost (+70% on haiku) and Stop latency (~20 s p95).
- **Placebo refeed.** Inject lines of the same length and position that list the fact and its source but *not* its qualifiers. This separates "a reminder of the fact" from "a reminder of the hedge."
- **Off under pressure.** The pilot ran Off on natural prompts only. Low is not a substitute: H3 assumes Low ≈ Off, and that was checked on 5 natural tasks with a ceiling.

**Medium bundles several manipulations.** Relative to Low it adds (a) a session line telling Claude a provenance file exists, (b) per-step delta lines that literally contain "source says: estimated", (c) the CSV path, and (d) the post-compaction digest. Any one could carry the effect. Claude never opened the CSV (0/24), so (c) is likely inert, but (a) is a standing instruction-like cue and (b) is a targeted echo. Ablate at least (a) vs (b).

**The echo problem.** Delta lines put the exact hedge token within a few thousand tokens of the answer. Lexical scoring then rewards the model for copying a recent token. That is not nothing — it may be the real mechanism, and a useful one — but say so plainly and test it against the placebo.

**High vs Medium is untestable as run.** High's retry fires only on a detected drop. Medium dropped nothing, so High had nothing to do: 5/5 vs 5/5 is a floor effect, not evidence that retry adds nothing. Test High only on tasks where Medium is known to drop.

## Tasks and corpus

The tasks make the target fact easy to find and the distractors easy to ignore, so they test recall of a salient token more than decay under realistic load.

- **Distractors are trivial.** `ops-1.md` is two lines: "Support closed 214 tickets in week 3." Fifteen of those add a few hundred tokens. "~15 steps" sounds like distance; in tokens it is short, and nothing competes with the revenue figure. Measure distance in tokens between read and answer, and report it.
- **The target is the only fact of its kind.** In `decay-finance-*` the only financial figures in context are the hedged ones. Real documents mix hedged and firm figures of the same type (Q2 actual, Q3 estimate). Add same-type competitors, some hedged and some firm, so keeping a hedge requires binding it to the right number.
- **Qualifiers sit in the same sentence as the figure.** "Q3 revenue is estimated at $4.2M" is the easiest possible case. Harder and more realistic: hedge in a heading or footnote ("All figures below are preliminary"), in a different paragraph, scoped over a table, or inherited through a citation chain.
- **The question names the fact.** "Give me Fernwick's Q3 revenue and revenue growth" points straight at the hedged figures. Ask open questions ("write the board summary") where the model chooses which facts to state.
- **Pressure prompts conflict with the construct** (see construct validity). Split them into format pressure ("one-line headline", "table, nothing else") and explicit anti-hedging ("no hedging"), and analyze them separately.
- **Ceiling on natural prompts.** Off kept 4/5. Natural-prompt results will mostly measure noise until tasks are harder.
- **Author-written, single domain.** One person wrote corpus, prompts, answer keys, plugin and scorer; every file is a fictional company memo in the same register. Have someone else write a held-out set, and include real documents (papers, earnings releases, news) with naturally occurring hedges.
- **Answer keys encode the author's lexicon.** `kept`/`dropped` examples in each TOML use exactly the hedge words the plugin's lexicon detects. Paraphrased hedges ("subject to audit", "not yet final") are absent, so the lexicon is never tested where it is weakest.

## Scoring and circularity

The judge is built from the defendant's parts. `eval/score.py` imports `qlaudified.indexer`, `qlaudified.lexicon`, `qlaudified.verify.claims` and `verify_answer`. Whatever hedges the plugin can't see, the scorer can't see either, and "verifier accuracy" is partly the verifier agreeing with itself.

- **Shared blind spots.** If the lexicon misses "subject to audit", the plugin won't refeed it and the scorer won't count it as dropped. Both errors cancel and the result looks clean.
- **"Ledger accuracy 100%" is graded against keys the same author wrote with the same lexicon.** It shows the pipeline is internally consistent, not that it finds the facts a human would mark.
- **Verifier accuracy is measured on the same runs used to tune the verifier.** The digit-in-filename and number-as-topic bugs were fixed after seeing decay runs. Fine as development; it means verifier numbers on those tasks are training accuracy.
- **No human labels.** The 50-claim human set was cut. Without it, no metric in the study is validated.
- **Scoring decisions are still open after seeing data.** The three questions in `sprint-6.md` ("~", next-sentence hedges, weaker hedges) move Low-under-pressure from 14% to ~43%. You noticed this, which is good; deciding it now, after the pilot, is still a researcher degree of freedom.

**Fix.**

1. Write an independent scorer: a separate lexicon (e.g. from a published hedge-cue resource such as the BioScope/CoNLL-2010 cue lists), plus an LLM judge from a different model family with a fixed rubric (kept / inflated / deflated / omitted), blind to condition.
2. Hand-label 100–150 fact-answer pairs across conditions, blind to condition (strip `[F1]` markers and any plugin text first). Report agreement of each scorer with the human labels (Cohen's κ).
3. Freeze the scoring rules in a dated amendment before the next run, and score every condition with all three (rules, independent judge, humans on the subset).
4. Hold out verifier tuning: tasks used for fixing bugs don't count toward verifier accuracy.

## Statistics and sample size

The intervals in `sprint-6.md` look rigorous but carry almost no information. With 5–7 tasks, one run each, and Medium at 100%, the bootstrap is resampling a handful of numbers, most of them identical.

- **Too few units.** A percentile bootstrap over 5 tasks has at most 126 distinct resamples, and with Medium fixed at 100% every interval's upper edge is pinned. "[+71, +100] over 7 tasks" is a description of 7 data points, not an estimate. Bootstrap CIs are known to undercover badly below ~20 clusters.
- **One repeat.** Agent runs are stochastic. You can't separate task difficulty from run-to-run noise with one run per task and condition.
- **Facts are nested in tasks, tasks in task families.** `decay-finance-d0/d5/d15/d15c` share the same source sentence; they are not independent tasks. Resampling them as independent overstates precision. Resample at the family level, or fit a mixed model (condition fixed; family, task and fact random).
- **Ceilings break the arithmetic.** Paired differences when one arm is at 100% are bounded and skewed. Use a model for binary outcomes (mixed-effects logistic regression, or at minimum an exact McNemar-style test on paired facts) and report odds ratios.
- **Multiple comparisons.** Six hypotheses × two models × two prompt variants × several distance cuts is dozens of intervals. Name one primary endpoint and one primary contrast; treat the rest as secondary with a correction (Holm) or label them exploratory.
- **H3 is an equivalence claim on 5 tasks.** "Low and Off differ by less than 10 points" needs a TOST-style test with power to exclude ±10. With 5 facts it can't.
- **No power analysis.** The protocol sets the run count by budget. Instead, decide the smallest effect worth detecting (say 15 points against the prompt-only baseline), estimate variance from the pilot, and compute how many fact-runs that needs. Then check whether $25 buys it.
- **Pilot data reused.** 14 of the 28 decay runs in the pilot are the previous night's dry run. Keep pilot data out of the confirmatory analysis entirely.

## Pre-registration and research hygiene

The habits are right; the timeline undermines them. A protocol written, rewritten and then run within about 24 hours, by the person who built the system, with the scoring still open, is pre-registered in name more than in effect.

- **No external timestamp.** The protocol lives in a repo you can amend. Put the frozen version on OSF or AsPredicted (free, timestamped) before the confirmatory runs.
- **Same-day design change.** Revision 2 replaced revision 1 "before any study run," but after the Sprint 4 dry run had shown a ceiling. That dry run informed the redesign. Say so; it isn't wrong, but it is not data-blind.
- **The go/no-go rule was easy to pass.** "Low drops ≥20% under pressure" was always likely when the prompt says "no hedging." A gate that can't fail isn't a gate.
- **Prompts can be tuned to the result.** Pressure prompts were written after seeing that natural prompts hit the ceiling. Freeze the task set, and write any new tasks before running any condition on them.
- **Exploratory and confirmatory are mixed.** Keep three folders: dry runs, pilot, confirmatory. Only the last enters the paper's tables.
- **Blinding.** You read answers while fixing bugs, and you'll hand-label. Strip condition markers and shuffle before any human scoring.
- **Stopping and exclusions** are good as written ("repeats never chosen by results", failed runs rerun). Add: what counts as a failed run (a run that answers but ignores the task?), decided in advance.

## Cost, latency and missing harm measures

The study measures only the benefit. A tool that changes model output needs its harms measured with the same care, or the result is advertising.

**Harms not measured**

- **Over-hedging.** No task contains an unhedged fact, so the study can't detect Medium adding "estimated" to a firm number. Add firm facts to every task and score inflation and deflation.
- **Hedge leakage.** When a hedged and a firm figure sit together, does Medium's refeed spill the hedge onto the wrong one? Only competitor facts can show this.
- **Instruction compliance.** On style-constrained prompts, measure whether format instructions were followed (table only, one line). Medium's table answers may add text that breaks "nothing else."
- **Answer quality.** Did refeeding change correctness, length, or usefulness? A blind pairwise preference judgment (human or independent LLM) on a sample would show whether hedge preservation costs readability.
- **Task success.** Report whether each answer answered the question at all, per condition.

**Cost framing**

- **"Overhead vs Off" mixes two prices.** `total_cost_usd` is Claude Code's estimate for the agent; sidecar spend comes from your own `usage.jsonl`. They are on different bases and neither is an invoice. Report tokens (input, cached input, output) per component, and derive dollars from one published price table.
- **The headline overhead is on haiku,** where the sidecar dominates. The protocol rightly says NFR-1/2 come from Sonnet. Then don't quote +73% anywhere a reader might take it as the result; and report overhead on both models.
- **Latency is a cost.** Stop p95 of 13–25 s is the slowest thing a user will feel, and no NFR covers it. Report it next to the effect size, and compare it with rules-only refeed, which has none.
- **Benchmark noise.** Latency on a desktop with ~20% background load and Defender scanning is fine for development but not for a reported number. Run final latency benchmarks on CI runners or a quiet machine, with the environment stated.

## External validity and how to frame claims

Even a clean result here would be a claim about one harness, one model family and one author's corpus. That's acceptable if the write-up says exactly that and no more.

- **One vendor.** Haiku and Sonnet are the same family and likely share hedging behavior. A non-Claude model (through the core library, or an open model via Ollama) is the cheapest way to show the effect isn't Claude-specific.
- **One harness.** Claude Code's context handling, compaction and system prompt are part of the treatment. Say "in Claude Code" in the claim.
- **Thinking is invisible.** Thinking arrives redacted in `claude -p`, so "use tracking" sees only visible text. Any claim about where a hedge was lost mid-run is about visible steps only.
- **Synthetic stress, not base rate.** Pressure and decay tasks are designed to cause drops; they can't tell a user how often drops happen in normal work. Pair them with a small set of real tasks, even if only scored by hand.

**Claims the current data supports:** "In a pilot on haiku with author-written tasks, refeeding source qualifiers into Claude Code's context made final answers contain those qualifiers more often, including when the prompt asked for unhedged output."

**Claims it does not support yet:** that qlaudified improves faithfulness, that it beats a simple instruction, that the sidecar is necessary, that it has no downside, or that it generalizes beyond this corpus or model family.

## Fix list before the Sonnet runs

Do items 1–7 before spending any confirmatory budget; they are mostly writing and task design, not runs. Then rerun the haiku pilot (about $0.50–1.00) to check the new design works, and only then freeze and go.

- [ ] **1. Add conditions:** prompt-only, rules-only refeed, placebo refeed, and Off under pressure. Drop High from the primary analysis until there are tasks where Medium drops.
- [ ] **2. Split pressure prompts** into format pressure and explicit anti-hedging; score instruction compliance on both.
- [ ] **3. Change the outcome** from hedge presence to calibration: kept / inflated / deflated / omitted, per stated fact.
- [ ] **4. Add firm facts and competitors** to every task: same-type figures, some hedged and some not; hedges scoped by headings, footnotes and citation chains; open questions that don't name the fact.
- [ ] **5. Make distance real:** longer, plausible distractor documents; report distance in tokens.
- [ ] **6. Build an independent scorer** (separate hedge-cue list plus a different-family LLM judge, blind to condition) and keep the plugin's rules as a secondary score.
- [ ] **7. Freeze and timestamp** the protocol on OSF: one primary endpoint (calibration kept on decay and competitor tasks), one primary contrast (Medium vs prompt-only), a power estimate, exclusion rules, and the scoring rules.
- [ ] **8. Scale:** enough task families for ~20+ clusters, at least 3 repeats, analysed with a mixed-effects logistic model; pilot data excluded.
- [ ] **9. Validate:** 100–150 blind human labels, κ against each scorer.
- [ ] **10. Generalize:** a held-out task set written by someone else, a few real-document tasks, and one non-Claude model.
- [ ] **11. Report harms next to benefits:** over-hedging rate, compliance, latency, cost in tokens, in the same table as the headline.

If Medium beats prompt-only and rules-only on calibration without inflating firm facts, you have a real result. If prompt-only matches it, that's the more useful finding, and it tells you to ship the deterministic tier and drop the sidecar.

---

## Notes from checking the critique against the repo (Oct 9)

- **Confirmed:** `eval/score.py` imports `qlaudified.indexer`, `lexicon`, `text`,
  `verify.claims` and `verify_answer`.
- **Confirmed:** 8 of the 27 pressure prompts say "no hedging" outright (`decay-finance-*`,
  `multi-headcount`, `nosource-berlin`, `seed-conflict`, `single-uptime`); the rest are format
  pressure ("markdown table only", "one short line for a slide", "two-sentence summary"). The
  split in fix 2 can be read off the existing prompts.
- **Confirmed:** Off ran on natural prompts only; no prompt-only, rules-only or placebo condition
  exists.
- **Correction:** NFR-5 does cover Stop (p95 ≤ 30 s; pilot 8–25 s). The critique repeats a
  mistake that was in the findings at the time and is now fixed. Latency is still a cost to
  report next to the effect.
- **Not found:** no "50-claim human set" appears in the current docs; whatever the history, there
  are no human labels now.
- **Ollama is not installed** on the dev machine, so a non-Claude judge or agent needs a setup
  decision.

## Proposed plan

**Phase A: redesign (no plan usage).** Do it in a separate git worktree while any batch is
running, because eval runs load the working copy as the plugin.

1. **Conditions:** prompt-only (off + one system line via `--append-system-prompt`); rules-only
   (Medium with `backend = "none"`, which config already supports); placebo (refeed the fact and
   its source without the qualifier: a small flag in `qlaudified/inject.py`); Off under both
   prompt styles. High leaves the primary analysis.
2. **Outcome:** calibration per stated fact (kept / inflated / deflated / omitted), stated rate,
   instruction compliance; anti-hedging and format pressure analysed separately.
3. **Tasks:** firm facts and same-type competitors in every task; hedges scoped by headings,
   footnotes, tables and citation chains; open questions; realistic distractor documents with
   distance in tokens; paraphrased hedges ("subject to audit", "not yet final"). The current
   tasks are frozen as `v1-exploratory`.
4. **Independent scorer:** CoNLL-2010/BioScope cue list plus a blind LLM judge from another
   family with a fixed rubric; the plugin's rules become a secondary score.
5. **Statistics:** task families as clusters; mixed-effects logistic model; one primary endpoint
   (calibration kept) and one primary contrast (Medium vs prompt-only); power from the new pilot.
6. **Hygiene:** `eval/runs/{dry,pilot,confirmatory}/`; a written failed-run rule; frozen protocol.

**Phase B:** redesigned haiku pilot (~$0.50–1.00), then freeze and timestamp the protocol.
**Phase C:** confirmatory runs.

## Open decisions

1. **The judge (and non-Claude agent) from another model family:** install Ollama with an open
   model (free, local, slower), or an API key for another vendor.
2. **Pre-registration:** OSF or AsPredicted, on Dryden's account (the text can be drafted).
3. **Human labels:** 100–150 blind labels, about 2–3 hours; a shuffled sheet with condition
   markers stripped can be generated.
4. **Held-out tasks** written by someone else: who, or record it as a limitation.
5. **Schedule:** the confirmatory study likely moves past the Nov 22 v1 date. Either ship v1 with
   the pilot framing and run the study after, or move the date.

## Triage of the open decisions (Oct 9)

The fatal and severe items are fixed by work that needs no outside decisions: baselines, the
calibration outcome with firm facts, split pressure analysis, a scorer that doesn't import the
plugin, harder tasks, and more task families and repeats. The decisions above are downsized:

| Decision | Outcome | Replacement |
| --- | --- | --- |
| Judge from another model family | Dropped | Independent rule scorer (own cue list, no plugin imports) plus a condition-blind Claude judge; same-family bias stated as a limitation |
| OSF pre-registration | Dropped | Frozen protocol committed, tagged and pushed before the first confirmatory run |
| Held-out tasks by someone else | Dropped | All new tasks written before any condition runs on them; a few real-document tasks; author-written corpus stated as a limitation |
| Human labels | Downsized | 40–60 blind labels (~45 min) as a sanity check on the scorers, not a precise accuracy figure |
| Schedule | Open | Not a validity question |

