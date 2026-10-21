"""House-style prose check for docs/: py -3 scripts/lint_docs.py docs"""
import re
import sys
from pathlib import Path

WEASEL = ["may", "might", "could", "possibly", "perhaps", "appears", "appeared", "seems",
          "suggests", "suggest", "about", "roughly", "approximately", "up to", "estimated",
          "uncertain", "likely", "potentially"]
PATTERN = re.compile(r"\b(" + "|".join(re.escape(w) for w in WEASEL) + r")\b", re.IGNORECASE)

problems = 0
for path in sorted(Path(sys.argv[1] if len(sys.argv) > 1 else "docs").rglob("*.md")):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in PATTERN.finditer(line):
            print(f'{path.as_posix()}:{n}: "{m.group(1)}" is a weasel word (house style)')
            problems += 1
print("ok" if not problems else f"{problems} problems")
sys.exit(1 if problems else 0)
