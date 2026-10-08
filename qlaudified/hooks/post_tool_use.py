"""PostToolUse: capture spans from retrieval tools (CAP-1, CAP-6). Deltas (INJ-1) arrive in Sprint 2.

Every mode captures, Low included: Low means no injection or verification, not no trail.
"""

from qlaudified import capture, config, paths
from qlaudified.store import Store


def handle(payload: dict) -> dict | None:
    if not capture.is_retrieval(payload.get("tool_name") or "") or not payload.get("session_id"):
        return None
    project = paths.project_dir(payload)
    cfg = config.load(project, payload["session_id"])
    spans = capture.spans_from_tool_result(payload, project, cfg.lexicon())
    if spans:
        Store(paths.session_dir(payload["session_id"], payload)).add_spans(spans)
    return None
