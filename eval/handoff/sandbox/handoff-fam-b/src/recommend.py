"""Recommend the best-ranked intervention for an outcome.

The ranking is copied from analysis/ranking.csv as constants so that importing
this module does no file I/O. Rows are (rank, intervention, outcome), in rank order.
Regenerate the constants if analysis/ranking.csv changes.
"""

_RANKING = (
    (1, "Yoga", "fatigue"),
    (2, "Acupuncture", "chronic pain"),
    (3, "Music therapy", "agitation"),
    (4, "Nurse home visits", "hospital readmissions"),
    (5, "Massage therapy", "post-operative pain"),
    (6, "Dietitian counselling", "weight regain"),
    (7, "Pharmacist medication review", "adverse drug events"),
    (8, "Strength training", "frailty scores"),
    (9, "CBT for insomnia", "insomnia severity"),
    (10, "Mindfulness training", "anxiety"),
    (11, "Bladder training", "incontinence episodes"),
    (12, "Text-message reminders", "missed appointments"),
    (13, "Breathing exercises", "breathlessness"),
    (14, "Sleep hygiene coaching", "daytime sleepiness"),
    (15, "Light therapy", "seasonal depression scores"),
    (16, "Walking groups", "depressive symptoms"),
    (17, "Hearing aids", "cognitive decline"),
    (18, "Peer support groups", "loneliness scores"),
    (19, "Tai chi", "falls"),
    (20, "Hydration reminders", "urinary tract infections"),
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
