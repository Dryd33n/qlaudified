"""The provenance report per turn: summary line, the Administrator's summary, claim-by-claim
verdicts and the ledger of facts used (REP-2, REP-4).

Saved as ``reports/turn-<n>.md`` and ``.json`` in the session folder. The summary line is what
Stop shows the user; ``/qlaudified report`` prints the markdown.
"""

import json
from pathlib import Path

from qlaudified.records import asdict
from qlaudified.store import Claim, Span

# Problems first in the summary; supported last.
ORDER = ["contradicted", "qualifier-dropped", "unsupported", "source-changed", "unresolved",
         "partial", "inference", "not-checked", "supported"]
LABELS = {
    "contradicted": "contradicted", "qualifier-dropped": "qualifier dropped",
    "unsupported": "unsupported", "unresolved": "unresolved", "partial": "partly supported",
    "inference": "inference", "supported": "supported", "not-checked": "not checked",
    "source-changed": "source changed",
}
PROBLEMS = {"contradicted", "qualifier-dropped", "unsupported"}
TIERS = {"deterministic": "rules", "nli": "NLI", "llm": "LLM", "reread": "re-read"}


def summary_line(claims: list[Claim], skipped: int = 0) -> str:
    counts = {v: sum(c.verdict == v for c in claims) for v in ORDER}
    parts = []
    for verdict in ORDER:
        if not counts[verdict]:
            continue
        part = f"{counts[verdict]} {LABELS[verdict]}"
        if verdict == "qualifier-dropped":
            words = list(dict.fromkeys(w for c in claims if c.verdict == verdict
                                       for w in c.dropped_qualifiers[:1]))
            part += f" ({', '.join(words[:3])})"
        parts.append(part)
    noun = "claim" if len(claims) == 1 else "claims"
    head = f"qlaudified: {len(claims)} {noun} checked"
    if skipped:
        head += f" ({skipped} not checked)"
    tail = " · /qlaudified report" if any(c.verdict in PROBLEMS for c in claims) else ""
    return " · ".join([head, *parts]) + tail


def render_markdown(n: int, claims: list[Claim], spans: dict[str, Span], skipped: int = 0,
                    summary_issues: list[dict] | None = None, admin_summary: str = "",
                    ledger: list[Span] | None = None) -> str:
    out = [f"# qlaudified report · turn {n}", "", summary_line(claims, skipped), ""]
    if admin_summary:
        out += [admin_summary, ""]
    for i, claim in enumerate(claims, 1):
        tier = TIERS.get(claim.decided_by)
        by = f" ({tier})" if tier else ""
        out.append(f"{i}. **{LABELS.get(claim.verdict, claim.verdict)}**{by}: {claim.text}")
        if claim.dropped_qualifiers:
            out.append(f"   - dropped: {', '.join(claim.dropped_qualifiers)}")
        unresolved = claim.verdict == "unresolved"
        for span_id in claim.span_ids[:1] if unresolved else claim.span_ids:
            span = spans.get(span_id)
            if span is None:
                if claim.decided_by == "reread":  # a source re-read from disk, not a fact row
                    out.append(f"   - re-read: {span_id}")
                continue
            closest = "closest: " if unresolved else ""
            out.append(f"   - {closest}[{span_id}] {span.source} {span.locator}: "
                       f"\"{_quote(span.text)}\"")
        if not claim.span_ids and claim.verdict == "unsupported":
            out.append("   - no source in this session states this")
    if not claims:
        out.append("No critical claims in this answer.")
    if ledger:
        out += ["", "## Provenance ledger: facts used", "",
                "| Fact | Claim | Origin | Source | Source qualifiers | First use | Impact |",
                "| --- | --- | --- | --- | --- | --- | --- |"]
        for f in ledger:
            first = "–" if f.first_use_step is None else (
                f"step {f.first_use_step}: {f.first_use_qualifiers or 'no qualifier'}")
            cells = [f.span_id, _quote(f.text), f.category or "–", f"{f.source} {f.locator}",
                     f.qualifiers or "–", first, _quote(f.impact) if f.impact else "–"]
            out.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    if summary_issues:
        out += ["", "## WebFetch summaries that changed their page", ""]
        for issue in summary_issues:
            what = LABELS.get(issue["verdict"], issue["verdict"])
            dropped = issue["dropped_qualifiers"]
            extra = f" (dropped: {', '.join(dropped)})" if dropped else ""
            out.append(f"- **{what}**{extra}: [{issue['summary_span']}] the summary says "
                       f"\"{issue['text']}\"")
            for span_id in issue["span_ids"]:
                span = spans.get(span_id)
                if span is not None:
                    out.append(f"  - page [{span_id}] {span.locator}: \"{_quote(span.text)}\"")
    return "\n".join(out) + "\n"


def _quote(text: str) -> str:
    quote = " ".join(text.split())
    return quote if len(quote) <= 160 else quote[:159] + "…"


def write_turn_report(session_dir: Path, n: int, prompt_id: str, claims: list[Claim],
                      spans: dict[str, Span], skipped: int = 0, mode: str = "",
                      summary_issues: list[dict] | None = None, admin_summary: str = "",
                      ledger: list[Span] | None = None) -> Path:
    """Write reports/turn-<n>.md and .json; returns the markdown path."""
    folder = Path(session_dir) / "reports"
    folder.mkdir(exist_ok=True)
    md = folder / f"turn-{n}.md"
    md.write_text(render_markdown(n, claims, spans, skipped, summary_issues, admin_summary, ledger),
                  encoding="utf-8")
    data = {
        "turn": n, "prompt_id": prompt_id, "mode": mode, "skipped": skipped,
        "summary": summary_line(claims, skipped),
        "claims": [asdict(c) for c in claims],
        "summary_issues": summary_issues or [],
        "administrator_summary": admin_summary,
        "ledger": [asdict(f) for f in ledger or []],
        "spans": {k: {"source": s.source, "locator": s.locator, "text": s.text,
                      "qualifiers": s.qualifiers} for k, s in spans.items()},
    }
    (folder / f"turn-{n}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return md
