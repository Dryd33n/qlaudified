"""Build data/findings.json from abstracts/ (one record per study)."""
import json
import re
from pathlib import Path


def parse(path):
    fields = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition(": ")
        if sep and key in ("Intervention", "Outcome", "Participants", "Results"):
            fields[key] = value.strip()
    effect = re.search(r"by (.+?)%", fields["Results"]).group(1)
    try:
        effect = float(effect)
    except ValueError:
        pass
    return {"id": path.stem, "intervention": fields["Intervention"], "outcome": fields["Outcome"],
            "n": int(fields["Participants"]), "effect_pct": effect, "caveats": ""}  # TODO caveats


records = [parse(p) for p in sorted(Path("abstracts").glob("*.md"))]
Path("data").mkdir(exist_ok=True)
Path("data/findings.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
print(f"wrote {len(records)} records to data/findings.json")
