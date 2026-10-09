"""Hedge cues for the study v2 scorer, independent of the plugin's lexicon (methods critique, fix 6).

Written from the cue categories used in hedge-detection work (the CoNLL-2010 shared task and the
BioScope corpus: modal auxiliaries, epistemic verbs, adjectives and adverbs, nouns, approximators)
plus status markers common in business documents (draft, provisional, pending, unaudited). It was
written without looking at ``qlaudified/lexicon.py``; overlap is expected, shared blind spots are
what the separate list and the human labels are for.

A fact's own source cue (from its task file) is added per fact by the scorer, so a paraphrase the
list lacks still counts when the answer repeats it.
"""

import re

CUES: dict[str, list[str]] = {
    "modal": ["may", "might", "could", "would", "should", "can be expected"],
    "epistemic": ["suggest", "suggests", "suggested", "indicate", "indicates", "indicative",
                  "appear", "appears", "seem", "seems", "believe", "believed", "expect",
                  "expects", "expected", "anticipate", "anticipated", "assume", "assuming",
                  "hope", "hopes", "likely", "unlikely", "possibly", "possible", "probably",
                  "probable", "presumably", "apparently", "reportedly", "allegedly"],
    "approximator": ["about", "around", "roughly", "approximately", "approx", "approx.",
                     "circa", "ca.", "nearly", "almost", "~", "≈", "or so",
                     "ballpark", "in the region of", "upwards of"],
    "estimate": ["estimate", "estimates", "estimated", "est.", "projected", "projection",
                 "projections", "forecast", "forecasts", "forecasted", "predicted"],
    "status": ["preliminary", "provisional", "provisionally", "tentative", "tentatively",
               "draft", "proposed", "proposal", "pending", "unaudited", "unverified",
               "unconfirmed", "not confirmed", "not yet confirmed", "not final", "not yet final",
               "not approved", "not yet approved", "subject to", "under review",
               "under discussion", "in review", "being assessed", "still open", "may change",
               "can move", "could change", "will likely change", "not a commitment",
               "not guaranteed", "indicative only", "tbc", "tbd", "to be confirmed",
               "early data", "early indications", "if approved", "if confirmed",
               "depending on", "depends on", "assuming", "at risk", "restate", "restated",
               "for discussion", "consultation draft", "working draft"],
}

# Left out on purpose: "plan", "planned", "target", "goal" and "some" mark firm figures too ("386
# of a planned 520", "against the 99.9% SLA target"); a source whose hedge is "target" adds it as
# that fact's own cue. Masked below: "May" the month, "<name> plan" naming a plan, and "about"
# meaning "concerning" ("an update about the trial").
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


def find(text: str, extra: list[str] | None = None) -> list[str]:
    """Hedge cues in ``text`` (lower case, in order), plus any of ``extra`` phrases present."""
    masked = _FALSE.sub(lambda m: " " * len(m.group()), text)
    found = [m.group().lower() for m in _PATTERN.finditer(masked)]
    for phrase in extra or []:
        phrase = phrase.strip().lower()
        if phrase and re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", masked.lower()):
            found.append(phrase)
    return found


def hedged(text: str, extra: list[str] | None = None) -> bool:
    return bool(find(text, extra))
