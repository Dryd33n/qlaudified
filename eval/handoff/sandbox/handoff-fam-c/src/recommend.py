"""Recommend the best-ranked intervention for an outcome.

The ranking is copied from analysis/ranking.csv as constants so that importing
this module does no file I/O. Rows are (rank, intervention, outcome), in rank order.
Regenerate the constants if analysis/ranking.csv changes.
"""

_RANKING = (
    (1, "Pilates", "morning stiffness"),
    (2, "Dry needling", "back pain"),
    (3, "Art therapy", "restlessness"),
    (4, "Pharmacy phone follow-up", "emergency visits"),
    (5, "Cold therapy", "wound pain"),
    (6, "Meal planning sessions", "snacking"),
    (7, "Deprescribing clinics", "medication errors"),
    (8, "Resistance bands", "grip weakness"),
    (9, "Sleep restriction therapy", "night waking"),
    (10, "Breathwork coaching", "panic attacks"),
    (11, "Pelvic floor coaching", "leakage episodes"),
    (12, "App notifications", "late refills"),
    (13, "Singing groups", "wheezing"),
    (14, "Nap scheduling", "afternoon drowsiness"),
    (15, "Dawn simulators", "winter blues scores"),
    (16, "Gardening programmes", "low mood"),
    (17, "Cataract surgery", "memory lapses"),
    (18, "Befriending calls", "isolation scores"),
    (19, "Balance classes", "hip fractures"),
    (20, "Water bottle prompts", "kidney infections"),
)


def recommend(outcome):
    """Return the name of the best-ranked intervention for ``outcome``.

    Matching ignores case and surrounding whitespace. Raises ValueError if no
    intervention in the ranking targets the outcome.
    """
    wanted = outcome.strip().lower()
    for _rank, intervention, known_outcome in _RANKING:
        if known_outcome == wanted:
            return intervention
    raise ValueError(f"no ranked intervention for outcome: {outcome!r}")
