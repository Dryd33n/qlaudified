"""Rank interventions by pooled effect per $100 of cost per patient.

Pools data/findings.json by intervention (mean effect_pct, total n, study count),
joins costs.csv on intervention name, and writes analysis/ranking.csv.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "ranking.csv"

records = json.loads((ROOT / "data" / "findings.json").read_text(encoding="utf-8"))
with (ROOT / "costs.csv").open(encoding="utf-8", newline="") as f:
    costs = {row["intervention"]: float(row["cost_per_patient"]) for row in csv.DictReader(f)}

pooled = {}
for rec in records:
    entry = pooled.setdefault(rec["intervention"], {"outcome": rec["outcome"], "effects": [], "n": 0})
    entry["effects"].append(rec["effect_pct"])
    entry["n"] += rec["n"]

missing = sorted(set(pooled) - set(costs))
if missing:
    raise SystemExit(f"no cost for interventions: {', '.join(missing)}")

rows = []
for name, entry in pooled.items():
    cost = costs[name]
    if cost <= 0:
        raise SystemExit(f"non-positive cost for {name}: {cost}")
    mean_effect = sum(entry["effects"]) / len(entry["effects"])
    rows.append({
        "intervention": name,
        "outcome": entry["outcome"],
        "studies": len(entry["effects"]),
        "total_n": entry["n"],
        "mean_effect_pct": round(mean_effect, 2),
        "cost_per_patient": cost,
        "effect_per_100_usd": round(mean_effect / (cost / 100), 3),
    })

rows.sort(key=lambda r: r["effect_per_100_usd"], reverse=True)
for rank, row in enumerate(rows, start=1):
    row["rank"] = rank

fields = ["rank", "intervention", "outcome", "studies", "total_n",
          "mean_effect_pct", "cost_per_patient", "effect_per_100_usd"]
OUT.parent.mkdir(exist_ok=True)
with OUT.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(f"wrote {len(rows)} interventions to {OUT.relative_to(ROOT)}")
