"""Stop: verify the final answer (VER-1..3), save the turn report (REP-4), export provenance.csv.

Medium and High verify every turn and show a one-line summary to the user (``systemMessage``);
High also runs the LLM tier (one batched call). Low only records the answer, so
``/qlaudified report`` can verify it on request.

VER-4: in High, if a critical claim is contradicted or drops a qualifier, Stop blocks once with a
numbered list of the problems, and Claude revises its answer. The Stop that follows carries
``stop_hook_active``, and it never blocks, so a turn is retried at most once. The retry counts as
one ``--max-turns`` turn (Sprint 4 prep). Medium never blocks.
"""

from qlaudified import config, paths, report
from qlaudified.store import Store
from qlaudified.verify import claims


def handle(payload: dict) -> dict | None:
    session_id = payload.get("session_id")
    if not session_id:
        return None
    folder = paths.session_dir(session_id, payload)
    answer = payload.get("last_assistant_message") or ""
    cfg = config.load(paths.project_dir(payload), session_id)
    has_store = (folder / "index.sqlite").exists()
    # An answer with nothing checkable in a session with no sources leaves no trace.
    if not has_store and not any(claims.is_critical(c, cfg.critical_threshold, cfg.lexicon())
                                 for c in claims.extract_claims(answer)):
        return None
    store = Store(folder)
    turn = store.start_turn(payload.get("prompt_id") or "", answer)
    response = None
    if cfg.mode != config.Mode.LOW and answer.strip():
        from qlaudified import background
        from qlaudified.backends import get_backend
        from qlaudified.verify import verify_turn

        background.wait_for_pending(folder)
        backend = get_backend(cfg.backend, cfg.backend_model) if cfg.mode == config.Mode.HIGH else None
        result = verify_turn(store, turn, cfg, backend)
        report.write_turn_report(folder, turn.n, turn.prompt_id, result.claims, result.spans,
                                 result.skipped, str(cfg.mode), result.summary_issues)
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
