"""MessageDisplay: add inline markers to the displayed answer (REP-1).

Claude Code waits for this hook before showing each batch, so it does the minimum: no store means
no markers, and only spans with numbers are loaded. Whether a code fence is open carries over to
the next batch of the same message in ``display-fence``.
"""

from qlaudified import config, markers, paths
from qlaudified.store import Store


def handle(payload: dict) -> dict | None:
    session_id = payload.get("session_id")
    delta = payload.get("delta")
    if not session_id or not isinstance(delta, str) or not delta.strip():
        return None
    folder = paths.session_dir(session_id, payload)
    if not (folder / "index.sqlite").exists():
        return None
    cfg = config.load(paths.project_dir(payload), session_id)
    if cfg.mode == config.Mode.LOW:
        return None
    spans = Store(folder).spans(with_numbers=True)
    fence_file = folder / "display-fence"
    message = str(payload.get("message_id") or "")
    was_open = fence_file.exists() and fence_file.read_text(encoding="utf-8") == message
    marked, still_open = markers.add_markers(delta, spans, cfg.lexicon(), was_open)
    if still_open:
        fence_file.write_text(message, encoding="utf-8")
    elif was_open:
        fence_file.unlink(missing_ok=True)
    if marked == delta:
        return None
    return {"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": marked}}
