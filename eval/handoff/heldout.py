"""Build the held-out handoff family (fam-c) from fam-b: new names, a new hedged/firm split.

    py -3 eval/handoff/heldout.py    # writes sandbox/handoff-fam-c/ and tasks/handoff-fam-c.json
    py -3 eval/handoff/build.py      # then the prompts

The carry-over's matching was designed while looking at fam-a and fam-b, so a fair test needs a
family it was not tuned on. fam-c keeps fam-b's real pipeline output (data, ranking, code, the
linted report: no hedge notes anywhere, since fam-b's run stripped them) and changes what the
matching sees: every intervention and outcome is renamed throughout, and the hedged/firm split
is redrawn so that it is neither fam-b's nor its swap (fam-a). Each abstract's Results and
Conclusion sentences are rewritten for its new kind from the same sentence templates the
abstracts were generated with; effects, participants and follow-up are unchanged.
"""

import json
import random
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = "handoff-fam-b"
TASK = "handoff-fam-c"
SEED = 2027

RENAME = {  # fam-b (name, outcome) -> fam-c (name, outcome)
    ("Yoga", "fatigue"): ("Pilates", "morning stiffness"),
    ("Tai chi", "falls"): ("Balance classes", "hip fractures"),
    ("Acupuncture", "chronic pain"): ("Dry needling", "back pain"),
    ("Mindfulness training", "anxiety"): ("Breathwork coaching", "panic attacks"),
    ("CBT for insomnia", "insomnia severity"): ("Sleep restriction therapy", "night waking"),
    ("Nurse home visits", "hospital readmissions"): ("Pharmacy phone follow-up", "emergency visits"),
    ("Strength training", "frailty scores"): ("Resistance bands", "grip weakness"),
    ("Music therapy", "agitation"): ("Art therapy", "restlessness"),
    ("Text-message reminders", "missed appointments"): ("App notifications", "late refills"),
    ("Pharmacist medication review", "adverse drug events"): ("Deprescribing clinics",
                                                              "medication errors"),
    ("Walking groups", "depressive symptoms"): ("Gardening programmes", "low mood"),
    ("Massage therapy", "post-operative pain"): ("Cold therapy", "wound pain"),
    ("Peer support groups", "loneliness scores"): ("Befriending calls", "isolation scores"),
    ("Dietitian counselling", "weight regain"): ("Meal planning sessions", "snacking"),
    ("Hearing aids", "cognitive decline"): ("Cataract surgery", "memory lapses"),
    ("Light therapy", "seasonal depression scores"): ("Dawn simulators", "winter blues scores"),
    ("Bladder training", "incontinence episodes"): ("Pelvic floor coaching", "leakage episodes"),
    ("Breathing exercises", "breathlessness"): ("Singing groups", "wheezing"),
    ("Hydration reminders", "urinary tract infections"): ("Water bottle prompts",
                                                          "kidney infections"),
    ("Sleep hygiene coaching", "daytime sleepiness"): ("Nap scheduling", "afternoon drowsiness"),
}
# Focus kinds: fam-b has nurse visits, acupuncture, yoga firm and text reminders, peer support,
# pharmacist review hedged. fam-c mixes them: yoga, nurse visits, text reminders hedged.
FOCUS_HEDGED = {"Yoga", "Nurse home visits", "Text-message reminders"}

HEDGED = [
    "{I} may have reduced {o} by about {e}% compared with usual care.",
    "{I} appeared to reduce {o} by roughly {e}% relative to controls, though the estimate is uncertain.",
    "In the {i} group, {o} possibly fell by an estimated {e}%.",
    "{I} might reduce {o} by up to {e}%, the authors suggest.",
]
FIRM = [
    "{I} reduced {o} by {e}% compared with usual care.",
    "{I} cut {o} by {e}% relative to controls.",
    "In the {i} group, {o} fell by {e}%.",
    "{I} lowered {o} by {e}% over the follow-up period.",
]
CONCLUSION = {"hedged": "These results suggest {i} may be worth further study.",
              "firm": "The trial shows that {i} lowered {o}."}


def kinds(source: dict) -> dict[str, str]:
    """fam-c's kind per fam-b intervention name: focus as above, the rest redrawn."""
    rng = random.Random(SEED)
    rest = [i["name"] for i in source["interventions"] if not i["focus"]]
    rng.shuffle(rest)
    hedged = FOCUS_HEDGED | set(rest[:10 - len(FOCUS_HEDGED)])
    return {i["name"]: "hedged" if i["name"] in hedged else "firm" for i in source["interventions"]}


def lower(name: str) -> str:
    """The name mid-sentence ("randomised to pilates"); no fam-c name starts with an acronym."""
    return name[0].lower() + name[1:]


def renamer():
    """Replace names and outcomes (longest first, whole words, any case) in one pass."""
    table = {}
    for (old_name, old_out), (new_name, new_out) in RENAME.items():
        table[old_name.lower()] = new_name
        table[old_out.lower()] = new_out
    pattern = re.compile(r"(?<![\w-])(" + "|".join(
        re.escape(k) for k in sorted(table, key=len, reverse=True)) + r")(?![\w-])", re.IGNORECASE)

    def swap(m: re.Match) -> str:
        new = table[m.group().lower()]
        return new if m.group()[0].isupper() else new[0].lower() + new[1:]

    return lambda text: pattern.sub(swap, text)


def main() -> int:
    source = json.loads((HERE / "tasks" / f"{SOURCE}.json").read_text(encoding="utf-8"))
    kind = kinds(source)
    rename = renamer()
    src, dest = HERE / "sandbox" / SOURCE, HERE / "sandbox" / TASK
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("prompt-*.txt", "__pycache__"))
    old = {i["name"]: i for i in source["interventions"]}
    new_name = {n: RENAME[(n, i["outcome"])][0] for n, i in old.items()}
    rng = random.Random(SEED + 1)
    for path in sorted(dest.rglob("*")):
        if not path.is_file() or path.suffix not in (".md", ".csv", ".json", ".py", ".txt"):
            continue
        text = path.read_text(encoding="utf-8")
        if path.parent.name == "abstracts":
            item = old[re.search(r"^Intervention: (.+)$", text, re.MULTILINE).group(1)]
            name, outcome = RENAME[(item["name"], item["outcome"])]
            effect = int(re.search(r"by (?:[a-z ]+ )?(\d+)%", text).group(1))
            fill = {"I": name, "i": lower(name), "o": outcome, "e": effect}
            pool = HEDGED if kind[item["name"]] == "hedged" else FIRM
            text = rename(text)
            text = re.sub(r"^Results: .*$", "Results: " + rng.choice(pool).format(**fill), text,
                          flags=re.MULTILINE)
            text = re.sub(r"^Conclusion: .*$",
                          "Conclusion: " + CONCLUSION[kind[item["name"]]].format(**fill), text,
                          flags=re.MULTILINE)
        else:
            text = rename(text)
        path.write_text(text, encoding="utf-8", newline="\n")
    task = {"id": TASK, "family": "fam-c",
            "interventions": [{**i, "name": new_name[i["name"]],
                               "outcome": RENAME[(i["name"], i["outcome"])][1],
                               "kind": kind[i["name"]]} for i in source["interventions"]],
            "studies": [{**s, "intervention": new_name[s["intervention"]],
                         "kind": kind[s["intervention"]]} for s in source["studies"]],
            "frozen_from": f"{source['frozen_from']}; renamed and re-split from {SOURCE} by "
                           "eval/handoff/heldout.py"}
    (HERE / "tasks" / f"{TASK}.json").write_text(json.dumps(task, indent=2) + "\n",
                                                 encoding="utf-8", newline="\n")
    print(f"built {TASK} from {SOURCE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
