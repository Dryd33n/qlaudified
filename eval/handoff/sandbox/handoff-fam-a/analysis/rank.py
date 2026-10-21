"""Pool data/findings.json by intervention, join costs.csv, and rank by effect per $100 of cost.

Run from the project root: py -3 -I analysis/rank.py
Writes analysis/ranking.csv.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

findings = json.loads(Path("data/findings.json").read_text(encoding="utf-8"))

pooled = defaultdict(lambda: {"effects": [], "n": 0})
for rec in findings:
    group = pooled[rec["intervention"]]
    group["effects"].append(rec["effect_pct"])
    group["n"] += rec["n"]

with open("costs.csv", newline="", encoding="utf-8") as f:
    costs = {row["intervention"]: float(row["cost_per_patient"]) for row in csv.DictReader(f)}

missing = sorted(set(pooled) - set(costs))
if missing:
    raise SystemExit(f"no cost in costs.csv for: {', '.join(missing)}")

rows = []
for intervention, group in pooled.items():
    mean_effect = sum(group["effects"]) / len(group["effects"])
    cost = costs[intervention]
    rows.append({
        "intervention": intervention,
        "mean_effect_pct": mean_effect,
        "total_n": group["n"],
        "n_studies": len(group["effects"]),
        "cost_per_patient": cost,
        "effect_per_100_dollars": mean_effect * 100 / cost,
    })

rows.sort(key=lambda r: r["effect_per_100_dollars"], reverse=True)

fields = ["rank", "intervention", "mean_effect_pct", "total_n", "n_studies",
          "cost_per_patient", "effect_per_100_dollars"]
with open("analysis/ranking.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    for i, r in enumerate(rows, start=1):
        writer.writerow({
            "rank": i,
            "intervention": r["intervention"],
            "mean_effect_pct": f"{r['mean_effect_pct']:.2f}",
            "total_n": r["total_n"],
            "n_studies": r["n_studies"],
            "cost_per_patient": f"{r['cost_per_patient']:.2f}",
            "effect_per_100_dollars": f"{r['effect_per_100_dollars']:.3f}",
        })

print(f"wrote {len(rows)} interventions to analysis/ranking.csv")
