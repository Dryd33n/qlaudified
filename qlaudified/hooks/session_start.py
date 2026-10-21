"""SessionStart: tell Claude where the ledger is (RFD-1); after compaction, the digest (RFD-3);
that earlier sessions' ledgers hold qualified facts, which are carried over on a match (RFD-5).

Medium and High only: Low adds nothing to Claude's context. At startup the session's store and an
empty, read-only provenance.csv are created, so the path Claude is given exists from the start.
"""

from qlaudified import carry, config, digest, inject, paths
from qlaudified.store import Store


def handle(payload: dict) -> dict | None:
    session_id = payload.get("session_id")
    if not session_id:
        return None
    project = paths.project_dir(payload)
    cfg = config.load(project, session_id)
    if cfg.mode == config.Mode.LOW:
        return None
    folder = paths.session_dir(session_id, payload)
    store = Store(folder)
    csv_path = inject.csv_hint(folder, project)
    if payload.get("source") == "compact":
        text = digest.build_digest(store, cfg.digest_budget_chars, csv_path,
                                   placebo=cfg.refeed == "placebo")
        text = text or inject.session_line(csv_path)
    else:
        if not store.csv_path.exists():
            store.export_csv()
        text = inject.session_line(csv_path)
        note = carry.session_note(session_id, payload) if cfg.carry_budget_chars > 0 else ""
        text = f"{text}\n{note}" if note else text
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
