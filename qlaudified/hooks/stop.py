"""Stop: final synthesis (design revision 2, step 9).

In every mode: check the answer's claims against the ledger's facts, re-reading sources for claims
with no fact behind them (VER-1 to VER-3); the Provenance Administrator adds each used fact's effect
on the conclusion and a report summary (PROV-5, REP-2); the report is saved (REP-4) and a one-line
summary is shown to the user (not to Claude). High also runs the LLM tier on unresolved claims.

VER-4: in High, if a critical claim is contradicted or drops a qualifier, Stop blocks once with a
numbered list of the problems, and Claude revises its answer. The Stop that follows carries
``stop_hook_active``, and it never blocks, so a turn is retried at most once. The retry counts as
one ``--max-turns`` turn (Sprint 4 prep). Low and Medium never block.
"""

from qlaudified import config, indexer, paths, report
from qlaudified.store import Store
from qlaudified.verify import claims


def handle(payload: dict) -> dict | None:
    session_id = payload.get("session_id")
    if not session_id:
        return None
    folder = paths.session_dir(session_id, payload)
    answer = payload.get("last_assistant_message") or ""
    project = paths.project_dir(payload)
    cfg = config.load(project, session_id)
    has_store = (folder / "index.sqlite").exists()
    # An answer with nothing checkable in a session with no sources leaves no trace.
    if not has_store and not any(claims.is_critical(c, cfg.critical_threshold, cfg.lexicon())
                                 for c in claims.extract_claims(answer)):
        return None
    store = Store(folder)
    turn = store.start_turn(payload.get("prompt_id") or "", answer)
    response = None
    if answer.strip():
        from qlaudified import administrator, background
        from qlaudified.backends import get_backend
        from qlaudified.verify import log_usage, verify_turn

        background.wait_for_pending(folder)
        backend = get_backend(cfg.backend, cfg.backend_model)
        result = verify_turn(store, turn, cfg, backend if cfg.mode == config.Mode.HIGH else None,
                             project)
        # The final answer is the last use of every fact it states (the end of the decay curve).
        final_step = store.current_step() + 1
        facts = {f.span_id: f for f in store.spans()}
        for claim in result.claims:
            for fact_id in claim.span_ids:
                if fact_id in facts:
                    store.record_use(fact_id, final_step, "final answer",
                                     _qualifiers_near(claim.text, facts[fact_id], cfg.lexicon()))
        summary, usage = administrator.run_final(store, backend, result.claims, answer)
        if usage:
            log_usage(folder, {"tier": "administrator-report", "turn": turn.n,
                               "backend": backend.name, "model": getattr(backend, "model", ""),
                               **usage})
        used = {s.span_id: s for s in store.spans() if s.uses or s.span_id in result.spans}
        report.write_turn_report(folder, turn.n, turn.prompt_id, result.claims,
                                 {**result.spans, **used}, result.skipped, str(cfg.mode),
                                 result.summary_issues, summary, list(used.values()))
        if result.claims:
            response = {"systemMessage": report.summary_line(result.claims, result.skipped)}
        # Sidecar-only finds are reported, but only lexicon hedges and contradictions block:
        # live, the sidecar once called "due on" a qualifier (Sprint 4).
        sidecar_words = set(store.sidecar_qualifiers())
        problems = [c for c in result.claims if c.critical and (
            c.verdict == "contradicted" or c.verdict == "qualifier-dropped"
            and set(c.dropped_qualifiers) - sidecar_words)]
        if cfg.mode == config.Mode.HIGH and problems and not payload.get("stop_hook_active"):
            response = {"decision": "block", "reason": retry_reason(problems, result.spans),
                        "systemMessage": report.summary_line(result.claims, result.skipped)
                        + " · asking Claude to revise once"}
    store.export_csv()
    return response


def _qualifiers_near(claim: str, fact, lex) -> str:
    """Hedges in the clause of the claim that states the fact's value (one claim can state
    several facts, each with its own hedges); the whole claim when no clause holds the value."""
    from qlaudified import text
    from qlaudified.tracking import _CLAUSES

    values = text.split_numbers(fact.numbers)
    for clause in _CLAUSES.split(claim):
        if any(text.number_match(n, v) for n in text.numbers(text.clean(clause)) for v in values):
            hedges = indexer.find_hedges(clause, lex)
            return "; ".join(w for ws in hedges.values() for w in ws)
    hedges = indexer.find_hedges(claim, lex)
    return "; ".join(w for ws in hedges.values() for w in ws)


def retry_reason(problems, spans) -> str:
    """Facts only: each problem claim, what's wrong, and the source passage (VER-4)."""
    plural = "s" if len(problems) > 1 else ""
    lines = [("qlaudified checked the answer against the sources read in this session and found "
              f"{len(problems)} problem{plural}:")]
    for i, claim in enumerate(problems, 1):
        what = ("drops the source's qualifier " + ", ".join(f'"{w}"' for w in
                                                            claim.dropped_qualifiers)
                if claim.verdict == "qualifier-dropped" else "is contradicted by the source")
        lines.append(f'{i}. "{claim.text}" {what}.')
        for span_id in claim.span_ids[:2]:
            span = spans.get(span_id)
            if span is not None:
                text = " ".join(span.text.split())[:240]
                lines.append(f'   [{span_id} {span.source} {span.locator}] "{text}"')
    return "\n".join(lines)
