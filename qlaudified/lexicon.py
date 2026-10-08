"""Hedge lexicon v0, grouped by strength class (CAP-2). User-extendable via config.toml (CFG-2).

A qualifier counts as dropped when the span's strongest hedge class is missing from the claim.
"""

HEDGES: dict[str, list[str]] = {
    "modal": ["may", "might", "could", "possibly", "perhaps"],
    "estimate": ["estimated", "approximately", "about", "around", "roughly", "preliminary", "projected"],
    "attribution": ["reportedly", "allegedly", "according to", "claimed"],
    "likelihood": ["likely", "unlikely", "probably", "expected to"],
    "tentative": ["tentative", "provisional", "draft", "unconfirmed", "subject to change"],
}

# Strongest first; Sprint 1 settles the ordering.
STRENGTH_ORDER = ["attribution", "tentative", "estimate", "likelihood", "modal"]
