"""Stop: verify the final answer (VER-1..3), save the turn report (REP-4), export provenance.csv.

Medium and High verify every turn and show a one-line summary to the user (``systemMessage``).
Low only records the answer, so ``/qlaudified report`` can verify it on request. Stop never
blocks in Medium; the High retry (VER-4) arrives in Sprint 4.
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
        from qlaudified.verify import verify_turn

        result = verify_turn(store, turn, cfg)
        report.write_turn_report(folder, turn.n, turn.prompt_id, result.claims, result.spans,
                                 result.skipped, str(cfg.mode))
        if result.claims:
            response = {"systemMessage": report.summary_line(result.claims, result.skipped)}
    store.export_csv()
    return response
