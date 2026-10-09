"""BM25 candidate retrieval over stored spans, boosted by shared numbers and cited span IDs.

Standard library only, no embeddings. The index is built once per Stop and reused for every claim.
"""

import math
import re
from collections import Counter

from qlaudified import text
from qlaudified.store import Span

K1, B = 1.2, 0.75
NUMBER_BOOST = 3.0  # per shared normalized number or date
CITED_BOOST = 100.0  # the claim names the span ("[S3]"), so it goes first
_CITED = re.compile(r"\bF(\d+)\b")


class Index:
    def __init__(self, spans: list[Span]) -> None:
        self.spans = spans
        self.docs = [Counter(text.tokens(text.clean(s.text))) for s in spans]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if spans else 0.0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(spans)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.numbers = [text.split_numbers(s.numbers) for s in spans]
        self.by_id = {s.span_id: i for i, s in enumerate(spans)}

    def bm25(self, query: list[str], i: int) -> float:
        doc, length = self.docs[i], self.lengths[i]
        score = 0.0
        for t in set(query):
            f = doc.get(t, 0)
            if f:
                score += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * length / (self.avg or 1)))
        return score

    def top(self, claim: str, k: int = 5) -> list[tuple[Span, float]]:
        """The best k spans for a claim, highest score first; spans scoring 0 are left out."""
        query = text.tokens(text.clean(claim))
        nums = text.numbers(text.clean(claim))
        cited = {f"F{n}" for n in _CITED.findall(claim)}
        scored = []
        for i, span in enumerate(self.spans):
            score = self.bm25(query, i)
            score += NUMBER_BOOST * sum(
                any(text.number_match(n, m) for m in self.numbers[i]) for n in nums)
            if span.span_id in cited:
                score += CITED_BOOST
            if score > 0:
                scored.append((span, score))
        scored.sort(key=lambda pair: -pair[1])
        return scored[:k]


def top_spans(claim: str, spans: list[Span], k: int = 5) -> list[tuple[Span, float]]:
    return Index(spans).top(claim, k)
