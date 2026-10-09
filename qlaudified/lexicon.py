"""Hedge lexicon v0, grouped by strength class (CAP-2). User-extendable via config.toml (CFG-2).

A qualifier counts as dropped when the span's strongest hedge class is missing from the claim.
"""

HEDGES: dict[str, list[str]] = {
    "modal": ["may", "might", "could", "possibly", "perhaps"],
    "estimate": [
        "estimated", "estimate", "estimates", "approximately", "approx", "about", "around",
        "roughly", "preliminary", "projected",
    ],
    "attribution": ["reportedly", "allegedly", "according to", "claimed"],
    "likelihood": ["likely", "unlikely", "probably", "expected to", "usually", "typically"],
    "tentative": [
        "tentative", "tentatively", "provisional", "provisionally", "draft", "unconfirmed",
        "subject to change", "pending", "to be confirmed", "not yet confirmed", "not confirmed",
    ],
}

# Words that are hedges only in front of a number ("about 15 minutes", not "a memo about pricing").
NUMERIC_ONLY = {"about", "around", "approximately", "approx", "roughly"}

# Strongest first: dropping an attribution or a tentative status changes what a claim asserts more
# than dropping a modal does. Settled in Sprint 1; revisit with eval data in Sprint 5.
STRENGTH_ORDER = ["attribution", "tentative", "estimate", "likelihood", "modal"]


def merged(extra: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """The base lexicon plus config.toml additions; unknown classes are added as new classes."""
    out = {cls: list(words) for cls, words in HEDGES.items()}
    for cls, words in (extra or {}).items():
        out.setdefault(cls, [])
        out[cls] += [w.lower() for w in words if w.lower() not in out[cls]]
    return out


def strongest(classes: list[str] | set[str]) -> str | None:
    for cls in STRENGTH_ORDER:
        if cls in classes:
            return cls
    return next(iter(sorted(classes)), None)
