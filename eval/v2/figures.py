"""Figures in text: money, percentages, counts, durations and dates (study v2 scorer).

Deliberately independent of the plugin (methods critique, fix 6): nothing here imports
``qlaudified``, so the scorer cannot share the plugin's parsing blind spots.

``extract(text)`` returns every figure with its position: ``Figure(value, kind, start, end)``,
where ``value`` is a float (``kind`` "number", "money" or "percent") or an ISO date string
(``kind`` "date", "--MM-DD" when the year is missing). ``matches(figure, value, unit)`` says
whether a figure states a fact's value: money and percentages need their sign, numbers match
within 0.6% (so "$2.7 million" and "$2,700,000" agree, and "$52M" rounds "$51.9M" no further than a
reader would accept), and dates match on the day.
"""

import re
from dataclasses import dataclass

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"], 1)}
MONTHS |= {name[:3]: i for name, i in list(MONTHS.items())} | {"sept": 9}
SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9,
         "billion": 1e9}
TOLERANCE = 0.006

_MONTH = r"(?P<mon>" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
_DATE_MDY = re.compile(_MONTH + r"\s+(?P<day>\d{1,2})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?",
                       re.IGNORECASE)
_DATE_DMY = re.compile(r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH + r"(?:,?\s+(?P<year>\d{4}))?",
                       re.IGNORECASE)
_DATE_ISO = re.compile(r"\b(?P<year>\d{4})-(?P<m>\d{2})-(?P<day>\d{2})\b")
_NUMBER = re.compile(
    r"(?P<cur>\$|USD\s?)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<scale>thousand|million|billion|mn|bn|[kmb])(?![a-z]))?"
    r"(?P<pct>\s?%|\s?percent\b)?",
    re.IGNORECASE)
# Labels that carry digits but are not figures: Q3, FY2027, H1, v7.4, HB-204, ops-1.md.
_NOT_FIGURES = re.compile(r"\b(?:Q[1-4]|H[12]|FY\s?\d{2,4}|v\d+(?:\.\d+)*|[A-Z]{1,4}-\d+|"
                          r"[\w-]*\d[\w-]*\.(?:md|txt|csv|json|py))\b", re.IGNORECASE)


@dataclass(frozen=True)
class Figure:
    value: float | str
    kind: str  # number | money | percent | date
    start: int
    end: int


def _iso(year: str | None, month: int, day: str) -> str | None:
    d = int(day)
    if not 1 <= d <= 31 or not 1 <= month <= 12:
        return None
    return f"{year}-{month:02d}-{d:02d}" if year else f"--{month:02d}-{d:02d}"


def extract(text: str) -> list[Figure]:
    """Every figure in ``text``, left to right, with dates taking precedence over bare numbers."""
    taken: list[tuple[int, int]] = []
    out: list[Figure] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    for m in _NOT_FIGURES.finditer(text):
        taken.append(m.span())
    for pattern in (_DATE_ISO, _DATE_DMY, _DATE_MDY):
        for m in pattern.finditer(text):
            if not free(*m.span()):
                continue
            month = int(m.group("m")) if "m" in m.groupdict() and m.group("m") else \
                MONTHS[m.group("mon").lower().rstrip(".")]
            iso = _iso(m.group("year"), month, m.group("day"))
            if iso:
                out.append(Figure(iso, "date", *m.span()))
                taken.append(m.span())
    for m in _NUMBER.finditer(text):
        if not free(*m.span()):
            continue
        value = float(m.group("num").replace(",", ""))
        if m.group("scale"):
            value *= SCALE[m.group("scale").lower()]
        kind = "percent" if m.group("pct") else "money" if m.group("cur") else "number"
        if kind == "number" and re.match(r"\s*(?:dollars|USD)\b", text[m.end():], re.IGNORECASE):
            kind = "money"
        out.append(Figure(value, kind, *m.span()))
    return sorted(out, key=lambda f: f.start)


def matches(figure: Figure, value: float | str, unit: str) -> bool:
    """Does this figure state the fact's value? ``unit`` is the fact's unit from the task file."""
    if unit == "date":
        if figure.kind != "date":
            return False
        want = str(value)
        return figure.value == want or (str(figure.value).startswith("--")
                                        and want[4:] == str(figure.value)[1:])
    if figure.kind == "date" or isinstance(figure.value, str):
        return False
    if unit == "%":
        if figure.kind != "percent":
            return False
    elif figure.kind == "percent" or (unit != "USD" and figure.kind == "money"):
        return False  # 14% is not 14 batches, and $38 is not 38 kilometres
    target = float(value)
    if unit == "%":
        # Percentages agree at the fact's own precision: 99.95% is not "99.9%", 12% is "12%".
        decimals = len(str(value).split(".")[1]) if "." in str(value) else 0
        return abs(figure.value - target) < 0.5 * 10 ** -decimals + 1e-9
    if target == 0:
        return figure.value == 0
    return abs(figure.value - target) <= TOLERANCE * abs(target)
