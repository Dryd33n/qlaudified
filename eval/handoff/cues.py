"""Hedge cues for the eval scorer, independent of the plugin's lexicon.

Written from the cue categories used in hedge-detection work (the CoNLL-2010 shared task and the
BioScope corpus: modal auxiliaries, epistemic verbs, adjectives and adverbs, nouns, approximators)
plus status markers common in business documents (draft, provisional, pending, unaudited) and
hedges common in scientific findings. It was written without looking at ``qlaudified/lexicon.py``;
overlap is expected, shared blind spots are what reading cells by hand is for.

A word count is a weak measure of certainty: it counts commentary ("the board may ask") and misses
a hedge that changed meaning. Treat the scorer's numbers as a first pass.
"""

import re

CUES: dict[str, list[str]] = {
    "modal": ["may", "might", "could", "would", "should", "can be expected"],
    "epistemic": ["suggest", "suggests", "suggested", "suggesting", "suggestive", "indicate",
                  "indicates", "indicative", "appear", "appears", "appeared", "appearing", "seem",
                  "seems", "believe", "believed", "expect", "expects", "expected", "anticipate",
                  "anticipated", "assume", "assuming", "hope", "hopes", "likely", "unlikely",
                  "possibly", "possible", "probably", "probable", "presumably", "apparently",
                  "reportedly", "allegedly", "perhaps", "maybe", "potential", "potentially",
                  "hypothesize", "hypothesise", "hypothesized", "speculate", "speculative",
                  "uncertain", "unclear", "not clear", "point to", "points to", "consistent with",
                  "raises the possibility", "can help", "could help", "may help"],
    "approximator": ["about", "around", "roughly", "approximately", "approx", "approx.",
                     "circa", "ca.", "nearly", "almost", "~", "≈", "or so",
                     "ballpark", "in the region of", "upwards of", "up to", "relatively",
                     "modest", "modestly", "generally", "often", "sometimes", "tend", "tends",
                     "tended", "in part", "partly", "partially", "some evidence"],
    "estimate": ["estimate", "estimates", "estimated", "est.", "projected", "projection",
                 "projections", "forecast", "forecasts", "forecasted", "predicted"],
    "status": ["preliminary", "provisional", "provisionally", "tentative", "tentatively",
               "draft", "proposed", "proposal", "pending", "unaudited", "unverified",
               "unconfirmed", "not confirmed", "not yet confirmed", "not final", "not yet final",
               "not approved", "not yet approved", "subject to", "under review",
               "under discussion", "in review", "being assessed", "still open", "may change",
               "can move", "could change", "will likely change", "not a commitment",
               "not guaranteed", "indicative only", "indicatively", "tbc", "tbd", "to be confirmed",
               "early data", "early indications", "if approved", "if confirmed",
               "depending on", "depends on", "at risk", "restate", "restated",
               "for discussion", "consultation draft", "working draft"],
}

# Left out on purpose: "plan", "target", "goal" and "some" mark firm figures too, and
# "associated", "linked", "correlated" state associations plainly. Masked below: "May" the month,
# "<name> plan" naming a plan, and "about" meaning "concerning" ("an update about the trial").
_FALSE = re.compile(
    r"\bmay\s+\d{1,2}\b|\b\d{1,2}\s+may\b|\bmay\s+\d{4}\b"
    r"|\b(?:team|business|pricing|price|enterprise|regulatory|hiring|project)\s+plan\b"
    r"|\babout\s+(?:the|a|an|our|its|their|how|what|why|this|that)\b",
    re.IGNORECASE)

_ALL = sorted({c for words in CUES.values() for c in words}, key=len, reverse=True)
_PATTERN = re.compile(
    "|".join(r"(?<![\w])" + re.escape(c) + (r"(?![\w])" if c[-1].isalnum() else "")
             for c in _ALL),
    re.IGNORECASE)


def find(text: str) -> list[str]:
    """Hedge cues in ``text``, lower case, in order."""
    masked = _FALSE.sub(lambda m: " " * len(m.group()), text)
    return [m.group().lower() for m in _PATTERN.finditer(masked)]
