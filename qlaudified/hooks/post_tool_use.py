"""PostToolUse: capture spans from retrieval tools (CAP-1, CAP-6) and inject the delta (INJ-1, INJ-2).

Every mode captures, Low included: Low means no injection or verification, not no trail. In Medium
and High the spans this call added for this agent come back as ``additionalContext``; a subagent's
payload carries its ``agent_id``, so its delta lands in its own context.
"""

from qlaudified import capture, config, inject, paths
from qlaudified.store import Store


def handle(payload: dict) -> dict | None:
    if not capture.is_retrieval(payload.get("tool_name") or "") or not payload.get("session_id"):
        return None
    project = paths.project_dir(payload)
    cfg = config.load(project, payload["session_id"])
    spans = capture.spans_from_tool_result(payload, project, cfg.lexicon())
    if not spans:
        return None
    new = Store(paths.session_dir(payload["session_id"], payload)).add_new_spans(spans)
    if cfg.mode == config.Mode.LOW:
        return None
    delta = inject.build_delta(new, cfg.inject_budget_chars)
    if not delta:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": delta}}
