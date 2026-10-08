"""Stop: export provenance.csv for the turn (Sprint 1). Claim verification arrives in Sprint 2-4 (VER-1..4)."""

from qlaudified import paths
from qlaudified.store import Store


def handle(payload: dict) -> dict | None:
    session_id = payload.get("session_id")
    if not session_id:
        return None
    folder = paths.session_dir(session_id, payload)
    if (folder / "index.sqlite").exists():
        Store(folder).export_csv()
    return None
