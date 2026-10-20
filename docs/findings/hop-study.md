# Hop study (draft, Oct 20, 2026)

Why: the difficulty probe ([sprint-6.md](sprint-6.md)) found no hedge loss, but every task was one
hop (read, then restate) with the source still in context, and every source was written here. A
mentor's questions (what evaluation dataset? how many hops does an optimal solution take? how much
context?) point at both gaps. This study changes two things: the sources and their certainty labels
come from outside, and the number of hops is the variable.

## Sources

Pei & Jurgens, *Measuring Sentence-Level and Aspect-Level (Un)certainty in Science Communications*
(EMNLP 2021), MIT licence: real findings from paper abstracts and science news, each rated for
certainty by annotators (sentence level, 1-6) and per aspect (Number, Extent, Probability,
Condition, Suggestion, Framing). `eval/v2/hops_select.py` keeps 167 **hedged** findings (rated
<= 3.5, an aspect rated Uncertain, a cue the scorer can see) and 288 **firm** ones (rated >= 5,
nothing Uncertain, no cue) in `eval/v2/hops/data/findings.jsonl`. The dataset has finding sentences
only, not full abstracts, so each study file is the verbatim finding under a heading.

Known limit: requiring a visible cue keeps mostly explicit hedges ("may", "might", "likely"),
the easy kind. Widening to implied hedges needs the certainty-estimator scorer, and is a decision
to write down here before making it.

## What a hop is

One step in which the agent reads the previous artifact and writes the findings into a new one.
Each step names one input and one output, so the optimal solution takes exactly N hops.

| Hop | What | File |
| --- | --- | --- |
| 1 | notes from studies/ (the six sources) | `hops/01-notes.md` |
| 2..N-1 | N-2 re-encodings: CSV table, one-liners (<= 15 words), slide bullets, email, plain language, takeaways, FAQ, social post (<= 280 chars) | `hops/NN-<kind>.*` |
| N | briefing for a science policy adviser (always the final genre) | `hops/NN-briefing.md` |

N = 4 (baseline), 6, 8, 10. Four families of six studies (three hedged, three firm); the menu is
rotated two places per family so a hop kind isn't tied to a position, and longer chains extend
shorter ones. 16 tasks, built by `eval/v2/hops_build.py`.

**Variants** (same steps, different session boundaries):

- *relay*: each hop is a fresh session (`/new` in the prompt file), so the sources are out of
  context unless Claude reopens them (counted as re-reads). This is the case no earlier task tested
  and the one the refeed is for.
- *session*: all hops in one session, as before; the sources stay in context.

## Scoring

`eval/v2/hops_score.py` scores **every hop's artifact**, not only the answer: each study is found
by its ID and judged kept / inflated / omitted (hedged) or plain / deflated / omitted (firm). It
reports the final hop by N and variant, survival by hop, loss by hop kind, and re-reads.
`--estimator` adds Pei & Jurgens' own model (`pip install certainty-estimator`): the mean change
in predicted certainty from source to final hop, an outside check on the lexicon. Not yet run: the
model download was blocked where this was built.

## Run order

1. Ceiling check, off only, haiku: `py -3 eval/run.py --suite hops --set dry --repeats 1` (32
   runs, 4-10 calls each) then `py -3 eval/v2/hops_score.py --set dry`. Read a few artifacts by
   hand before trusting any number.
2. If off loses hedges as N grows (relay at least), add `--conditions off,prompt,placebo,medium`
   on the hop counts where loss shows. If it doesn't, that is the result: no loss up to 10 hops,
   even with the sources out of context.
3. Optional positive control: the same tasks on a local model through Ollama.

Checked before any live run: a stand-in `claude` that strips "may"/"might" at the one-liner hop
was caught at exactly that hop and nowhere else (unit tests in `tests/unit/test_eval_hops.py`).
