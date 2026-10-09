"""Long distractor documents for the long-horizon probe (protocol v2 ceiling gate).

Long sessions are simulated by reading, not by many calls: four generated documents of about 15k
tokens each (under Claude Code's single-read limit) put ~60k tokens between the source and the
question in a handful of calls, most of them cache hits. Reading tokens is cheap; calls and
output are what cost.

The documents are data appendices and meeting minutes for the same organisation, full of
**same-type competing figures** (other trials' spending, other depots' fuel, other segments'
ARR), about a fifth of them hedged. They are generated from a fixed seed, and every figure is
checked against the organisation's task facts so the scorer can never confuse the two.
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import figures

TARGET_CHARS = 56_000  # ~14k tokens per document
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September"]
PEOPLE = ["Ana Ruiz", "Ben Okafor", "Chloe Martin", "Dev Patel", "Eilidh Ross", "Femi Adeyemi",
          "Grace Liu", "Hassan Karimi", "Ines Duarte", "Jonas Berg", "Kira Novak", "Liam Byrne"]
HEDGES = [
    "though this is not yet confirmed", "subject to the quarter-end review",
    "based on preliminary figures", "pending sign-off from finance", "if current trends hold",
    "according to an early estimate", "though the number may be revised",
]

ORGS = {
    "Halden Biotech": {
        "entities": ["HB-118", "HB-311", "HB-402", "HB-515", "HB-627", "HB-733"],
        "entity_noun": "programme",
        "metrics": [
            ("spending", "USD", 200_000, 3_900_000), ("patients enrolled", "count", 15, 640),
            ("active sites", "count", 3, 58), ("open data queries", "count", 40, 2900),
            ("screen-failure rate", "%", 4, 38), ("monitoring visits", "count", 12, 410),
        ],
    },
    "Corran Logistics": {
        "entities": ["Leeds", "Bristol", "Glasgow", "Hull", "Derby", "Exeter", "Norwich",
                     "Carlisle"],
        "entity_noun": "depot",
        "metrics": [
            ("fuel spend", "USD", 90_000, 1_400_000), ("on-time rate", "%", 81, 99),
            ("average delivery time in hours", "count", 11, 44),
            ("pallets moved", "count", 2_000, 88_000), ("damage claims", "count", 4, 150),
            ("driver vacancies", "count", 1, 35),
        ],
    },
    "Maple Street Council": {
        "entities": ["Northgate ward", "Riverside ward", "Hillside ward", "Old Town ward",
                     "Eastfield ward", "Westbridge ward"],
        "entity_noun": "ward",
        "metrics": [
            ("repair spending", "USD", 60_000, 900_000), ("potholes fixed", "count", 40, 1900),
            ("library visits", "count", 900, 31_000), ("bus journeys", "count", 5_000, 240_000),
            ("planning applications", "count", 8, 190), ("recycling rate", "%", 31, 62),
        ],
    },
    "Brightwater Software": {
        "entities": ["SMB", "mid-market", "enterprise", "education", "public sector", "EMEA",
                     "North America", "APAC"],
        "entity_noun": "segment",
        "metrics": [
            ("ARR", "USD", 1_100_000, 29_000_000), ("gross churn", "%", 2, 14),
            ("net revenue retention", "%", 88, 131), ("new customers", "count", 12, 640),
            ("paid seats", "count", 1_500, 92_000), ("support tickets", "count", 300, 9_800),
        ],
    },
}


def _render(value: float, unit: str) -> str:
    if unit == "USD":
        return f"${value / 1e6:.2f}M" if value >= 1_000_000 else f"${value:,.0f}"
    if unit == "%":
        return f"{value:.1f}%"
    return f"{value:,.0f}"


class _Figures:
    """Draws figures that never state any of the facts to avoid."""

    def __init__(self, rng: random.Random, avoid: list[dict]):
        self.rng, self.avoid = rng, avoid

    def draw(self, unit: str, lo: float, hi: float) -> str:
        for _ in range(200):
            value = self.rng.uniform(lo, hi)
            if unit == "USD":
                value = round(value, -4) if value >= 1_000_000 else round(value, -3)
            elif unit == "%":
                value = round(value, 1)
            else:
                value = round(value)
            text = _render(value, unit)
            found = figures.extract(text)
            if not any(figures.matches(f, fact["value"], fact["unit"]) for f in found
                       for fact in self.avoid):
                return text
        raise RuntimeError("could not draw a figure clear of the task facts")


def _table(org: dict, figs: _Figures, rng: random.Random, title: str) -> str:
    metrics = rng.sample(org["metrics"], 3)
    head = f"| {org['entity_noun'].capitalize()} | Month | " + " | ".join(m[0] for m in metrics) + " |"
    lines = [f"## {title}", "", head, "| " + " | ".join(["---"] * (len(metrics) + 2)) + " |"]
    for entity in org["entities"]:
        for month in MONTHS:
            cells = [figs.draw(unit, lo, hi) for _, unit, lo, hi in metrics]
            if rng.random() < 0.12:
                cells[rng.randrange(len(cells))] += " (provisional)"
            lines.append(f"| {entity} | {month} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _minutes(org: dict, figs: _Figures, rng: random.Random, title: str, n: int) -> str:
    lines = [f"## {title}", ""]
    for _ in range(n):
        person, entity = rng.choice(PEOPLE), rng.choice(org["entities"])
        name, unit, lo, hi = rng.choice(org["metrics"])
        month = rng.choice(MONTHS)
        value = figs.draw(unit, lo, hi)
        if rng.random() < 0.2:
            lines.append(f"{person} said {name} for the {entity} {org['entity_noun']} could reach "
                         f"about {value} by the end of the year, {rng.choice(HEDGES)}.")
        else:
            other = figs.draw(unit, lo, hi)
            lines.append(f"{person} reported that {name} for the {entity} {org['entity_noun']} was "
                         f"{value} in {month}, compared with {other} a year earlier.")
    return "\n".join(lines) + "\n"


def documents(org_name: str, avoid: list[dict], seed: int = 2026) -> dict[str, str]:
    """Four long documents for the organisation, each about ``TARGET_CHARS`` long."""
    org = ORGS[org_name]
    rng = random.Random(f"{seed}-{org_name}")
    figs = _Figures(rng, avoid)
    out = {}
    for i, name in enumerate(["appendix-a.md", "appendix-b.md", "minutes-c.md", "minutes-d.md"]):
        kind = "data appendix" if i < 2 else "meeting minutes"
        parts = [f"# {org_name}: {kind} {'ABCD'[i]}\n"]
        k = 0
        while sum(len(p) for p in parts) < TARGET_CHARS:
            k += 1
            if i < 2 or k % 3 == 0:
                parts.append(_table(org, figs, rng, f"Table {'ABCD'[i]}{k}"))
            else:
                parts.append(_minutes(org, figs, rng, f"Meeting {'ABCD'[i]}{k}", 40))
        out[name] = "\n".join(parts)
    return out
