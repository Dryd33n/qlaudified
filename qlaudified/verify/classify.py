"""Final labels for claims no tier decided: unsupported, inference or unresolved (VER-2).

- unsupported: no candidate span, a number or date found in no span, or little word overlap.
- inference: no single passage covers the claim, but its top spans together do.
- unresolved: some overlap, nothing decisive; tier 3 (``report --deep``, Sprint 3) can settle it.
"""

from qlaudified import text
from qlaudified.store import Span

UNSUPPORTED_BELOW = 0.3
INFERENCE_COMBINED = 0.7


def classify(claim: str, decided: dict | None, candidates: list[tuple[Span, float]]) -> dict:
    if decided is not None:
        return decided
    cleaned = text.clean(claim)
    claim_tokens = text.tokens(cleaned)
    top = [span for span, _ in candidates[:3]]
    per_span = [set(text.tokens(text.clean(s.text))) for s in top]
    best = max((text.coverage(claim_tokens, t) for t in per_span), default=0.0)
    combined = text.coverage(claim_tokens, set().union(*per_span)) if per_span else 0.0

    def label(verdict: str, spans: list[Span], confidence: float, by: str) -> dict:
        return {"verdict": verdict, "span_ids": [s.span_id for s in spans],
                "dropped_qualifiers": [], "decided_by": by, "confidence": round(confidence, 2)}

    if not top or text.numbers(cleaned) or best < UNSUPPORTED_BELOW and combined < UNSUPPORTED_BELOW:
        return label("unsupported", [], 0.6 if top else 0.8, "deterministic")
    if len(top) > 1 and combined >= INFERENCE_COMBINED and best < INFERENCE_COMBINED:
        return label("inference", top, combined * 0.6, "deterministic")
    return label("unresolved", top, best * 0.5, "none")
