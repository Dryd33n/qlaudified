"""Verification pipeline: claims -> candidates -> tier 1 -> tier 2 (NLI) -> tier 3 (LLM) -> classify.

Sprint 2 runs claims, BM25 candidates, tier 1 and classify; tiers 2 and 3 arrive in Sprint 3.
"""

import time
from dataclasses import dataclass, field

from qlaudified.config import Config, Mode
from qlaudified.store import Claim, Span, Store, Turn


@dataclass
class TurnResult:
    turn: Turn
    claims: list[Claim]
    skipped: int  # non-critical claims left unchecked
    spans: dict[str, Span] = field(default_factory=dict)
    elapsed_ms: float = 0.0


def threshold(cfg: Config) -> float:
    """High checks more: half the threshold lets plain claims through, not just critical ones."""
    return cfg.critical_threshold / 2 if cfg.mode == Mode.HIGH else cfg.critical_threshold


def verify_answer(answer: str, spans: list[Span], turn: Turn, cfg: Config) -> tuple[list[Claim], int]:
    from qlaudified.verify import candidates, claims, classify, tier1

    lex = cfg.lexicon()
    limit = threshold(cfg)
    index = candidates.Index(spans)
    out: list[Claim] = []
    skipped = 0
    for claim_text, sentence in claims.claims_in_context(answer):
        score = claims.criticality(claim_text, lex)
        if score < limit:
            skipped += 1
            continue
        found = index.top(claim_text, k=5)
        decided = tier1.check(claim_text, [s for s, _ in found], lex, context=sentence)
        result = classify.classify(claim_text, decided, found)
        out.append(Claim(
            claim_id=f"C{turn.n}.{len(out) + 1}", turn=turn.prompt_id, text=claim_text,
            span_ids=result["span_ids"], verdict=result["verdict"],
            dropped_qualifiers=result["dropped_qualifiers"], decided_by=result["decided_by"],
            confidence=result["confidence"], critical=score >= cfg.critical_threshold,
        ))
    return out, skipped


def verify_turn(store: Store, turn: Turn, cfg: Config) -> TurnResult:
    """Verify a turn's answer against the session's spans and store the claims (VER-1..3)."""
    start = time.perf_counter()
    spans = store.spans()
    found, skipped = verify_answer(turn.answer, spans, turn, cfg)
    store.add_claims(turn.prompt_id, found)
    used = {i for c in found for i in c.span_ids}
    return TurnResult(turn, found, skipped, {s.span_id: s for s in spans if s.span_id in used},
                      (time.perf_counter() - start) * 1000)
