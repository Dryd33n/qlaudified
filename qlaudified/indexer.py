"""Span indexer: numbers, dates, units and hedge words for a passage (CAP-2).

Numbers are normalized so different spellings compare equal in Tier 1: ``$4.2M`` and
``4.2 million USD`` both become ``4200000 USD``; durations become seconds, so ``15 minutes`` and
``900 seconds`` both become ``900 s``. Dates become ISO (``2026-09-30``, ``2027-01``, ``2027``,
and ``--11-18`` for a month and day with no year).
"""

import re

from qlaudified.lexicon import HEDGES, NUMERIC_ONLY

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
# Capitalized only, so the hedge "may" is never read as a month.
_MONTH = (
    r"(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
_DATE_PATTERNS = [
    re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
    re.compile(_MONTH + r"\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})\b"),
    re.compile(r"\b(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH + r",?\s+(?P<y>\d{4})\b"),
    re.compile(r"\b" + _MONTH + r",?\s+(?P<y>\d{4})\b"),
    # Month and day with no year: "--11-18", ISO 8601's yearless form.
    re.compile(_MONTH + r"\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?\b(?!,?\s+\d{4})"),
    re.compile(r"\b(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH + r"\b(?!,?\s+\d{4})"),
]

MAGNITUDES = {
    "k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9,
    "billion": 1e9, "t": 1e12, "trillion": 1e12,
}
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
CURRENCY_CODES = {"usd", "eur", "gbp", "cad", "aud", "jpy", "chf"}
SECONDS = {
    "ms": 0.001, "millisecond": 0.001, "milliseconds": 0.001, "s": 1, "sec": 1, "secs": 1,
    "second": 1, "seconds": 1, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "h": 3600,
    "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}
_UNITS = "|".join(sorted([*SECONDS, *CURRENCY_CODES, "percent", "per cent"], key=len, reverse=True))
_NUMBER = re.compile(
    r"(?<![\w.])(?P<cur>[$€£])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<mag>thousand|million|billion|trillion|bn|(?-i:MM|[kKMBT]))(?![A-Za-z]))?"
    r"(?:\s?(?P<pct>%)|\s(?P<unit>" + _UNITS + r")\b)?",
    re.IGNORECASE,
)


def _fmt(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


_URL = re.compile(r"https?://\S+|\]\([^)]*\)")


def _strip_urls(text: str) -> str:
    """URLs and markdown link targets hold IDs and anchors, not facts."""
    return _URL.sub(lambda m: " " * len(m.group()), text)


def _date_spans(text: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            if any(s < m.end() and m.start() < e for s, e, _ in found):
                continue
            groups = m.groupdict()
            if groups.get("m"):
                month = int(groups["m"])
            else:
                mon = groups["mon"].lower()
                month = MONTHS["sept" if mon.startswith("sept") else mon[:3]]
            iso = f"{groups['y']}-{month:02d}" if groups.get("y") else f"--{month:02d}"
            if groups.get("d"):
                iso += f"-{int(groups['d']):02d}"
            found.append((m.start(), m.end(), iso))
    return sorted(found)


def _parse(m: re.Match) -> tuple[float, str] | None:
    """(value, unit) for one number match; unit is '' for plain counts."""
    value = float(m["num"].replace(",", ""))
    if m["mag"]:
        value *= MAGNITUDES[m["mag"].lower()]
    unit = ""
    if m["cur"]:
        unit = CURRENCY_SYMBOLS[m["cur"]]
    raw_unit = (m["unit"] or "").lower()
    if m["pct"] or raw_unit in ("percent", "per cent"):
        unit = "%"
    elif raw_unit in CURRENCY_CODES:
        unit = raw_unit.upper()
    elif raw_unit in SECONDS:
        value *= SECONDS[raw_unit]
        unit = "s"
    return value, unit


def normalize_number(text: str) -> float | None:
    """'$4.2M' and '4.2 million USD' -> 4200000.0; '15 minutes' -> 900.0 (seconds)."""
    m = _NUMBER.search(text)
    if not m:
        return None
    parsed = _parse(m)
    return parsed[0] if parsed else None


def extract_dates(text: str) -> list[str]:
    """ISO dates in order of appearance, plus bare years (1900-2099) that aren't amounts."""
    text = _strip_urls(text)
    out = [iso for _, _, iso in _date_spans(text)]
    masked = _mask(text, _date_spans(text))
    for m in _NUMBER.finditer(masked):
        if _is_year(m):
            out.append(m["num"])
    return list(dict.fromkeys(out))


def extract_numbers(text: str) -> list[str]:
    """Normalized amounts such as '4200000 USD', '900 s', '12 %' or '48'; dates excluded."""
    text = _strip_urls(text)
    out = []
    for m in _NUMBER.finditer(_mask(text, _date_spans(text))):
        if _is_year(m):
            continue
        parsed = _parse(m)
        if parsed:
            value, unit = parsed
            out.append(f"{_fmt(value)} {unit}".strip())
    return list(dict.fromkeys(out))


def _mask(text: str, spans: list[tuple[int, int, str]]) -> str:
    for start, end, _ in spans:
        text = text[:start] + " " * (end - start) + text[end:]
    return text


def _is_year(m: re.Match) -> bool:
    num = m["num"]
    return (len(num) == 4 and num.isdigit() and 1900 <= int(num) <= 2099
            and not (m["cur"] or m["mag"] or m["pct"] or m["unit"]))


def find_hedges(text: str, lexicon: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Hedge class -> matched words, lowercased, in lexicon order."""
    out: dict[str, list[str]] = {}
    for cls, words in (lexicon or HEDGES).items():
        for word in words:
            pattern = r"(?<![\w-])" + re.escape(word).replace(r"\ ", r"\s+") + r"(?![\w-])"
            if word in NUMERIC_ONLY:
                pattern += r"(?=\s*[$€£]?\d)"
            if re.search(pattern, text, re.IGNORECASE):
                out.setdefault(cls, []).append(word)
    return out
