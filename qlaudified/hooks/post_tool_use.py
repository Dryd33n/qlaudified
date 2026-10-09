"""PostToolUse: capture spans from retrieval tools (CAP-1, CAP-6) and inject the delta (INJ-1, INJ-2).

Every mode captures, Low included: Low means no injection or verification, not no trail. In Medium
and High the spans this call added for this agent come back as ``additionalContext``; a subagent's
payload carries its ``agent_id``, so its delta lands in its own context. A new WebFetch summary
also starts the raw-page re-fetch (CAP-3).
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
    folder = paths.session_dir(payload["session_id"], payload)
    store = Store(folder)
    new = store.add_new_spans(spans)
    if cfg.mode == config.Mode.LOW:
        return None
    for span in new:
        if span.origin == "web-summary":  # the page itself, in a detached process (CAP-3)
            from qlaudified import refetch

            refetch.start(folder, project, span.source, span.span_id, span.agent_id, span.turn)
    extra: list[str] = []
    if cfg.mode == config.Mode.HIGH:
        from qlaudified import sidecar  # SID-1, SID-2: in the background, results come next call

        sidecar.start(folder, project, new)
        for line in sidecar.format_lines(store.take_sidecar(payload.get("agent_id") or "main")):
            if sum(len(x) + 1 for x in extra) + len(line) <= cfg.inject_budget_chars // 2:
                extra.append(line)
    budget = cfg.inject_budget_chars - sum(len(x) + 1 for x in extra)
    delta = "\n".join([*extra, inject.build_delta(new, budget)]).strip()
    if not delta:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": delta}}
