"""PostToolUse: one step of the Provenance Administrator's loop (design revision 2, steps 5–8).

For every tool call: number the step; parse what a retrieval returned into facts and log the
source (INT, PROV-1); track uses of earlier facts and Claude's own claims in its reasoning and
the tool input (INT-3, PROV-4); let the Administrator fill the judgment fields when the step meets
the threshold (PROV-2 to PROV-6); rewrite the read-only provenance.csv (PROV-7). In Medium and High
the new facts go back to Claude as plain factual lines (RFD-2); Low adds nothing to Claude's context.
Reads of provenance.csv itself are logged as consults (RFD-4), never captured.
"""

import json
import time

from qlaudified import capture, config, inject, paths, tracking
from qlaudified.store import Store


def _consult(payload: dict) -> bool:
    ti = json.dumps(payload.get("tool_input") or {})
    return "provenance.csv" in ti and ".qlaudified" in ti.replace("\\\\", "/")


def _tool_input_text(payload: dict) -> str:
    ti = payload.get("tool_input") or {}
    return str(ti.get("command") or ti.get("file_path") or ti.get("pattern") or ti.get("url")
               or ti.get("query") or json.dumps(ti))


def handle(payload: dict) -> dict | None:
    session_id = payload.get("session_id")
    tool = payload.get("tool_name") or ""
    if not session_id or not tool:
        return None
    project = paths.project_dir(payload)
    folder = paths.session_dir(session_id, payload)
    cfg = config.load(project, session_id)
    lex = cfg.lexicon()
    agent = payload.get("agent_id") or "main"
    turn = payload.get("prompt_id")
    retrieval = capture.is_retrieval(tool)
    if not retrieval and not (folder / "index.sqlite").exists():
        return None  # nothing read yet, so nothing to track
    store = Store(folder)
    step = store.next_step(payload.get("tool_use_id") or f"{tool}-{time.time()}", tool, agent)

    if _consult(payload):
        response = payload.get("tool_response")
        with open(folder / "consults.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "step": step,
                                "tool": tool, "agent_id": agent,
                                "chars": len(json.dumps(response)) if response else 0}) + "\n")
        return None

    new = []
    if retrieval:
        facts, sources = capture.read_tool_result(payload, project, lex, store.provided(), step)
        store.add_sources(sources)
        new = store.add_new_spans(facts)

    scan = tracking.scan(store.spans(), step, tracking.pieces(payload, project), lex)
    for use in scan.uses:
        store.record_use(use.fact.span_id, step, use.where, use.qualifiers)
    claims = store.add_new_spans(tracking.claim_rows(scan.claims, step, agent, turn, lex))

    if new or scan.uses or claims:
        from qlaudified import administrator
        from qlaudified.backends import get_backend

        backend = get_backend(cfg.backend, cfg.backend_model)
        usage = administrator.run_step(store, backend, step, tool, _tool_input_text(payload), new,
                                       scan, claims)
        if usage:
            from qlaudified.verify import log_usage

            log_usage(folder, {"tier": "administrator", "step": step, "backend": backend.name,
                               "model": getattr(backend, "model", ""), **usage})

    for span in new:
        if span.origin == "web-summary":  # the page itself, in a background job (CAP-3)
            from qlaudified import refetch

            refetch.start(folder, project, span.source, span.span_id, span.agent_id, span.turn)
    if new or scan.uses or claims or not store.csv_path.exists():
        store.export_csv()  # most tool calls change nothing; skip the rewrite then

    if cfg.mode == config.Mode.LOW or not new:
        return None
    current = {s.span_id: s for s in store.spans()}  # after the Administrator's changes
    kept = [current[s.span_id] for s in new if s.span_id in current]
    delta = inject.build_delta(kept, cfg.inject_budget_chars, csv_path=inject.csv_hint(folder, project),
                               placebo=cfg.refeed == "placebo")
    if not delta:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": delta}}
