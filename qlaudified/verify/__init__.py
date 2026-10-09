"""Verification pipeline: claims -> candidates -> tier 1 -> tier 2 (NLI) -> tier 3 (LLM) -> classify.

Tier 1 (rules) always runs. Tier 2 runs when the ``[nli]`` extra and its model are installed.
Tier 3 runs only when a backend is passed: ``/qlaudified report --deep`` in Medium, every Stop in
High (VER-3). Each claim records which tier decided it.
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from qlaudified import text
from qlaudified.config import Config, Mode
from qlaudified.store import Claim, Span, Store, Turn

# Claims the LLM tier gets a second look at; rule-decided problems stand as they are.
FOR_LLM = {"unresolved", "partial", "inference", "unsupported"}


@dataclass
class TurnResult:
    turn: Turn
    claims: list[Claim]
    skipped: int  # non-critical claims left unchecked
    spans: dict[str, Span] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    usage: dict = field(default_factory=dict)  # the LLM call, if any
    summary_issues: list[dict] = field(default_factory=list)  # WebFetch summary vs its page


def threshold(cfg: Config) -> float:
    """High checks more: half the threshold lets plain claims through, not just critical ones."""
    return cfg.critical_threshold / 2 if cfg.mode == Mode.HIGH else cfg.critical_threshold


def evidence(spans: list[Span]) -> list[Span]:
    """Spans claims are checked against. A WebFetch summary whose page was re-fetched gives way to
    the raw page, so a qualifier the summary dropped is still seen (CAP-3)."""
    fetched = {s.source for s in spans if s.origin == "web-raw"}
    # Claude's own claims are what's being checked, never evidence for themselves.
    return [s for s in spans if s.origin != "claude"
            and not (s.origin == "web-summary" and s.source in fetched)]


def reread_sources(store: Store, project) -> tuple[list[Span], set[str], bool]:
    """Passages of the local files Claude read, read again from disk (VER-3).

    Returns (passages, sources that changed since Claude read them, whether every source read
    could be re-read). Facts are all that's stored; claims without a number, date or qualifier
    are checked against these. Command output and MCP results can't be re-read, and web pages
    contribute only their facts, so a session with those sources isn't fully re-readable."""
    from pathlib import Path

    from qlaudified.capture import _hash

    passages: list[Span] = []
    changed: set[str] = set()
    complete = True
    cache: dict[str, list[str] | None] = {}
    for src in store.sources():
        if src.rereadable != "file":
            complete = False
            continue
        if src.source not in cache:
            try:
                cache[src.source] = (Path(project) / src.source).read_text(
                    encoding="utf-8", errors="replace").splitlines()
            except OSError:
                cache[src.source] = None
        lines = cache[src.source]
        m = re.fullmatch(r"L(\d+)(?:-L(\d+))?", src.locator)
        if lines is None or not m:
            changed.add(src.source)
            continue
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        body = "\n".join(lines[a - 1:b])
        if _hash(body) != src.hash:
            changed.add(src.source)
            continue
        passages.append(Span(f"{src.source} {src.locator}", src.origin, src.source, src.locator,
                             body, hash=src.hash))
    return passages, changed, complete


def summary_issues(spans: list[Span], cfg: Config) -> list[dict]:
    """Sentences of a WebFetch summary that drop a qualifier or contradict the re-fetched page:
    the qualifier was lost before Claude ever saw it (CAP-3)."""
    from qlaudified.verify import claims, tier1

    lex = cfg.lexicon()
    raw_by_url: dict[str, list[Span]] = {}
    for s in spans:
        if s.origin == "web-raw":
            raw_by_url.setdefault(s.source, []).append(s)
    issues = []
    for summary in spans:
        page = raw_by_url.get(summary.source)
        if summary.origin != "web-summary" or not page:
            continue
        from qlaudified.verify.candidates import Index

        index = Index(page)
        for claim_text, sentence in claims.claims_in_context(summary.text):
            if claims.criticality(claim_text, lex) < 0.7:
                continue
            found = [s for s, _ in index.top(claim_text, k=3)]
            result = tier1.check(claim_text, found, lex, context=sentence) if found else None
            if result and result["verdict"] in ("qualifier-dropped", "contradicted"):
                issues.append({"summary_span": summary.span_id, "url": summary.source,
                               "text": claim_text, **result})
    return issues


def verify_answer(answer: str, spans: list[Span], turn: Turn, cfg: Config, backend=None,
                  extra_qualifiers: list[str] | None = None,
                  reread: tuple[list[Span], set[str], bool] | None = None) -> tuple[list[Claim], int]:
    from qlaudified.verify import candidates, claims, classify, tier1, tier2_nli, tier3_llm

    lex = cfg.lexicon()
    if extra_qualifiers:  # the High sidecar's finds count like lexicon hedges (SID-2)
        lex["sidecar"] = [q for q in extra_qualifiers if q not in lex.get("sidecar", [])]
    limit = threshold(cfg)
    index = candidates.Index(evidence(spans))
    nli_ready: bool | None = None  # loaded on the first claim the rules leave undecided (~2 s)
    out: list[Claim] = []
    found_for: dict[str, list[Span]] = {}
    skipped = 0
    for claim_text, sentence in claims.claims_in_context(answer):
        score = claims.criticality(claim_text, lex)
        if score < limit:
            skipped += 1
            continue
        found = index.top(claim_text, k=5)
        decided = tier1.check(claim_text, [s for s, _ in found], lex, context=sentence)
        if decided is None and found:
            if nli_ready is None:
                nli_ready = tier2_nli.available()
            if nli_ready:
                decided = tier2_nli.check(claim_text, [s for s, _ in found[:3]])
        result = classify.classify(claim_text, decided, found)
        no_figures = not text.numbers(text.clean(claim_text))
        weak = result["verdict"] in ("unsupported", "unresolved", "partial")
        if weak and reread is not None and no_figures:
            result = _check_reread(claim_text, sentence, reread, lex) or result
        claim = Claim(
            claim_id=f"C{turn.n}.{len(out) + 1}", turn=turn.prompt_id, text=claim_text,
            span_ids=result["span_ids"], verdict=result["verdict"],
            dropped_qualifiers=result["dropped_qualifiers"], decided_by=result["decided_by"],
            confidence=result["confidence"], critical=score >= cfg.critical_threshold,
        )
        out.append(claim)
        found_for[claim.claim_id] = [s for s, _ in found[:3]]

    if backend is not None:
        pending = [c for c in out if c.verdict in FOR_LLM and found_for[c.claim_id]]
        items = [tier3_llm.item(c.claim_id, c.text, found_for[c.claim_id]) for c in pending]
        for claim, verdict in zip(pending, tier3_llm.check_batch(items, backend), strict=False):
            if verdict is not None:
                claim.verdict = verdict["verdict"]
                claim.span_ids = verdict["span_ids"]
                claim.dropped_qualifiers = verdict["dropped_qualifiers"]
                claim.decided_by = "llm"
                claim.confidence = verdict["confidence"]
    return out, skipped


def _check_reread(claim: str, sentence: str, reread: tuple[list[Span], set[str], bool],
                  lex) -> dict | None:
    """A claim with no fact behind it, checked against the re-read sources (VER-3)."""
    from qlaudified.verify import tier1

    passages, changed, complete = reread
    decided = tier1.check(claim, passages, lex, context=sentence) if passages else None
    if decided is not None:
        decided["decided_by"] = "reread"  # span_ids are "path L4-L6": sources, not fact rows
        return decided
    if changed or not complete:
        verdict = "source-changed" if changed and complete else "not-checked"
        return {"verdict": verdict, "span_ids": sorted(changed)[:3], "dropped_qualifiers": [],
                "decided_by": "reread", "confidence": 0.0}
    return None


def verify_turn(store: Store, turn: Turn, cfg: Config, backend=None,
                project=None) -> TurnResult:
    """Verify a turn's answer against the ledger's facts, re-reading sources for claims with no
    fact behind them, and store the claims (VER-1 to VER-3)."""
    start = time.perf_counter()
    spans = store.spans()
    reread = reread_sources(store, project) if project is not None else None
    found, skipped = verify_answer(turn.answer, spans, turn, cfg, backend,
                                   store.sidecar_qualifiers(), reread)
    store.add_claims(turn.prompt_id, found)
    used = {i for c in found for i in c.span_ids}
    usage = dict(getattr(backend, "last_usage", {}) or {}) if backend is not None else {}
    if usage:
        log_usage(store.session_dir, {"turn": turn.n, "backend": backend.name,
                                      "model": getattr(backend, "model", ""),
                                      "claims": sum(c.decided_by == "llm" for c in found), **usage})
    issues = summary_issues(spans, cfg)
    used |= {i for issue in issues for i in [issue["summary_span"], *issue["span_ids"]]}
    return TurnResult(turn, found, skipped, {s.span_id: s for s in spans if s.span_id in used},
                      (time.perf_counter() - start) * 1000, usage, issues)


def log_usage(session_dir: Path, record: dict) -> None:
    """One line per LLM call in usage.jsonl: cost, tokens, wall time (design.md, data model)."""
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **record}
    with open(Path(session_dir) / "usage.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
