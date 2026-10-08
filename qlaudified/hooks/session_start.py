"""SessionStart: after compaction (``source: compact``), re-inject the digest (INJ-3)."""

from qlaudified import config, digest, paths
from qlaudified.store import Store


def handle(payload: dict) -> dict | None:
    session_id = payload.get("session_id")
    if payload.get("source") != "compact" or not session_id:
        return None
    folder = paths.session_dir(session_id, payload)
    if not (folder / "index.sqlite").exists():
        return None
    cfg = config.load(paths.project_dir(payload), session_id)
    if cfg.mode == config.Mode.LOW:
        return None
    text = digest.build_digest(Store(folder), cfg.digest_budget_chars)
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
