"""Recommend the best-ranked intervention for a study outcome.

The constants below are copied from analysis/ranking.csv (rank by effect per $100)
and from the outcome column of data/findings.json (which intervention was studied
for each outcome). Nothing is read from disk at import time.
"""

# Intervention -> rank in analysis/ranking.csv (1 is best).
INTERVENTION_RANK = {
    "Yoga": 1,
    "Acupuncture": 2,
    "Music therapy": 3,
    "Nurse home visits": 4,
    "Massage therapy": 5,
    "Dietitian counselling": 6,
    "Pharmacist medication review": 7,
    "Strength training": 8,
    "CBT for insomnia": 9,
    "Mindfulness training": 10,
    "Bladder training": 11,
    "Text-message reminders": 12,
    "Breathing exercises": 13,
    "Sleep hygiene coaching": 14,
    "Light therapy": 15,
    "Walking groups": 16,
    "Hearing aids": 17,
    "Peer support groups": 18,
    "Tai chi": 19,
    "Hydration reminders": 20,
}

# Outcome -> interventions studied for it in data/findings.json.
OUTCOME_INTERVENTIONS = {
    "adverse drug events": ("Pharmacist medication review",),
    "agitation": ("Music therapy",),
    "anxiety": ("Mindfulness training",),
    "breathlessness": ("Breathing exercises",),
    "chronic pain": ("Acupuncture",),
    "cognitive decline": ("Hearing aids",),
    "daytime sleepiness": ("Sleep hygiene coaching",),
    "depressive symptoms": ("Walking groups",),
    "falls": ("Tai chi",),
    "fatigue": ("Yoga",),
    "frailty scores": ("Strength training",),
    "hospital readmissions": ("Nurse home visits",),
    "incontinence episodes": ("Bladder training",),
    "insomnia severity": ("CBT for insomnia",),
    "loneliness scores": ("Peer support groups",),
    "missed appointments": ("Text-message reminders",),
    "post-operative pain": ("Massage therapy",),
    "seasonal depression scores": ("Light therapy",),
    "urinary tract infections": ("Hydration reminders",),
    "weight regain": ("Dietitian counselling",),
}


def recommend(outcome):
    """Return the best-ranked intervention studied for `outcome`.

    Raises ValueError if no study covers the outcome.
    """
    key = outcome.strip().lower()
    candidates = OUTCOME_INTERVENTIONS.get(key)
    if not candidates:
        raise ValueError(f"no intervention studied for outcome: {outcome!r}")
    return min(candidates, key=INTERVENTION_RANK.__getitem__)
