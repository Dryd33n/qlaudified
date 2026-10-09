"""LLM tier: one batched call per turn with a strict JSON schema (VER-3).

Only claims the rules couldn't settle go in (unresolved, partial, inference, and unsupported
claims that have candidate passages), each with its top passages. The model may only cite the
passages it was given; anything else in its answer is dropped, and an invalid or missing answer
leaves the claim as the rules labelled it.
"""

from qlaudified.store import Span

MAX_CLAIMS = 20
PASSAGE_CHARS = 600
VERDICTS = ["supported", "partial", "qualifier-dropped", "contradicted", "unsupported", "inference"]

SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string", "enum": VERDICTS},
                    "span_ids": {"type": "array", "items": {"type": "string"}},
                    "dropped_qualifiers": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["id", "verdict", "span_ids", "dropped_qualifiers", "confidence"],
            },
        },
    },
    "required": ["verdicts"],
}

INSTRUCTIONS = """\
You check claims from an AI assistant's answer against source passages it read. For each claim,
use only the passages listed under it, never outside knowledge.

Verdicts:
- supported: a passage states the claim, with the same hedging.
- qualifier-dropped: a passage states it, but hedged ("estimated", "may", "pending",
  "according to", ...) and the claim drops that hedge. List the dropped words.
- partial: passages support part of the claim only.
- contradicted: a passage states something incompatible (a different number, date or fact).
- inference: no passage states it, but it follows from the passages together.
- unsupported: the passages don't support it.

Cite the passage IDs you relied on in span_ids. confidence is 0 to 1. Answer for every claim ID.
"""


def build_prompt(items: list[dict]) -> str:
    parts = [INSTRUCTIONS]
    for item in items:
        parts.append(f"\nClaim {item['id']}: {item['claim']}")
        for span in item["spans"]:
            text = " ".join(span.text.split())[:PASSAGE_CHARS]
            parts.append(f"  [{span.span_id}] ({span.source} {span.locator}) {text}")
    return "\n".join(parts) + "\n"


def item(claim_id: str, claim: str, spans: list[Span]) -> dict:
    return {"id": claim_id, "claim": claim, "spans": spans}


def check_batch(items: list[dict], backend) -> list[dict | None]:
    """One call for all items; a verdict per item in order, or None where the model gave none."""
    items = items[:MAX_CLAIMS]
    if not items:
        return []
    answer = backend.complete_json(build_prompt(items), SCHEMA)
    rows = answer.get("verdicts") if isinstance(answer, dict) else None
    by_id = {r.get("id"): r for r in rows if isinstance(r, dict)} if isinstance(rows, list) else {}
    out: list[dict | None] = []
    for it in items:
        row = by_id.get(it["id"])
        if not row or row.get("verdict") not in VERDICTS:
            out.append(None)
            continue
        allowed = {s.span_id for s in it["spans"]}
        try:
            confidence = max(0.0, min(1.0, float(row.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append({
            "verdict": row["verdict"],
            "span_ids": [] if row["verdict"] == "unsupported" else
                        [s for s in row.get("span_ids") or [] if s in allowed],
            "dropped_qualifiers": [str(w) for w in row.get("dropped_qualifiers") or []
                                   if row["verdict"] == "qualifier-dropped"],
            "decided_by": "llm",
            "confidence": round(confidence, 2),
        })
    return out
