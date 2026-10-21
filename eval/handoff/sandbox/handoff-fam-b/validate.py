"""Check data/findings.json against the findings schema; exit 1 on any error."""
import json
import sys
from pathlib import Path

REQUIRED = {"id": str, "intervention": str, "outcome": str, "n": int, "effect_pct": (int, float)}

records = json.loads(Path("data/findings.json").read_text(encoding="utf-8"))
studies = {p.stem for p in Path("abstracts").glob("*.md")}
errors = []
for rec in records:
    rid = rec.get("id", "?")
    for key, kind in REQUIRED.items():
        if key not in rec:
            errors.append(f"{rid}: missing {key}")
        elif not isinstance(rec[key], kind) or isinstance(rec[key], bool):
            errors.append(f"{rid}: {key} must be a number, got {rec[key]!r}" if key == "effect_pct"
                          else f"{rid}: {key} has the wrong type")
    for key in rec:
        if key not in REQUIRED:
            errors.append(f"{rid}: unknown field {key}")
if {r.get("id") for r in records} != studies or len(records) != len(studies):
    errors.append(f"expected one record per study ({len(studies)}), got {len(records)}")
for line in errors[:20]:
    print(line)
if len(errors) > 20:
    print(f"... and {len(errors) - 20} more")
print("ok" if not errors else f"{len(errors)} errors")
sys.exit(1 if errors else 0)
