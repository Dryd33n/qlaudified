"""The Provenance Administrator: the sidecar that fills REQ-3.2's judgment fields (PROV-2 to PROV-6).

Rules have already filled the exact fields (claim, value, source, line, source qualifiers, uses).
Per step that meets the threshold (new facts, uses of tracked facts, or Claude's own claims),
one synchronous call to a small model (haiku by default, or Ollama) decides:

- which new facts are critical, and qualifiers the word list missed (kept only if verbatim);
- the origin of Claude's own claims: Model Inference, Training Data or Hybrid, with the primary
  source and whether sources agreed, for hybrids;
- the operational impact of each use: how the fact fed this step.

At Stop, one more call writes each used fact's effect on the conclusion and a short report
summary. Inputs stay small (only what the step touched, capped), and the instructions and schema
come first and never change, so repeated calls can reuse the prompt cache. With no backend
(``none``, or offline), rows keep their rule fields and Claude's claims stay "Unclassified".
"""

from qlaudified import lexicon
from qlaudified.store import Span, Store
from qlaudified.tracking import Scan

ORIGINS = ["Model Inference", "Training Data", "Hybrid"]
REASONING_CHARS = 1200
TOOL_INPUT_CHARS = 400
MAX_ITEMS = 25

STEP_INSTRUCTIONS = """\
You are the Provenance Administrator for an AI research agent. You keep a ledger of critical
facts: figures, dates and conditions whose exact wording and qualifiers matter. For one step of
the agent's work you get: the facts it just read (F...), facts it reused (U...), and statements it
made that match no source it read (C...). Answer in the JSON schema, for every ID:

- F: critical (true/false: false only for trivia like version numbers, step counts, page
  numbers); extra_qualifiers: words in that sentence that make it less certain or conditional
  ("unaudited", "in beta", "if approved") and are not in this list: {known}. Copy them exactly.
- C: origin: "Model Inference" (derived by reasoning or arithmetic from the ledger's facts),
  "Training Data" (general knowledge, not from any ledger fact), or "Hybrid" (both);
  primary_source: the F-ID that mainly drove it, or ""; sources_agree: "yes", "no" or "".
- U: impact: how the agent used the fact in this step, at most 15 words.
Be brief: no explanations beyond the fields.
"""

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "critical": {"type": "boolean"},
            "extra_qualifiers": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "critical", "extra_qualifiers"]}},
        "claims": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "origin": {"type": "string", "enum": ORIGINS},
            "primary_source": {"type": "string"},
            "sources_agree": {"type": "string", "enum": ["yes", "no", ""]}},
            "required": ["id", "origin", "primary_source", "sources_agree"]}},
        "uses": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "impact": {"type": "string"}},
            "required": ["id", "impact"]}},
    },
    "required": ["facts", "claims", "uses"],
}

FINAL_INSTRUCTIONS = """\
You are the Provenance Administrator for an AI research agent. Below are the critical facts in
its ledger that it used, how it used them, and its final answer with each claim's verdict.
- For each fact: final_impact, its effect on the final conclusion, at most 20 words.
- summary: at most 3 sentences and 60 words in total, in the third person: what the answer rests
  on, which qualifiers survived or were lost, and what a reader should double-check. Describe the
  record, not your own process.
"""

FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "final_impact": {"type": "string"}},
            "required": ["id", "final_impact"]}},
        "summary": {"type": "string"},
    },
    "required": ["facts", "summary"],
}


def needs_call(new: list[Span], scan: Scan, claim_rows: list[Span]) -> bool:
    """The threshold (PROV-6): something critical happened in this step."""
    return bool(new or scan.uses or claim_rows)


def _line(span: Span) -> str:
    quals = f" [source qualifiers: {span.qualifiers}]" if span.qualifiers else ""
    return f"{' '.join(span.text.split())}{quals} ({span.source} {span.locator})"


def step_prompt(step: int, tool: str, tool_input: str, new: list[Span], scan: Scan,
                claim_rows: list[Span], ledger: list[Span]) -> str:
    known = ", ".join(sorted({w for ws in lexicon.HEDGES.values() for w in ws}))
    lines = [STEP_INSTRUCTIONS.format(known=known), f"Step {step}, tool: {tool}"]
    if tool_input:
        lines.append(f"Tool input: {' '.join(tool_input.split())[:TOOL_INPUT_CHARS]}")
    if scan.reasoning:
        lines.append(f"Agent's reasoning before the call: {scan.reasoning[-REASONING_CHARS:]}")
    for span in new[:MAX_ITEMS]:
        lines.append(f"{span.span_id}: {_line(span)}")
    for i, use in enumerate(scan.uses[:MAX_ITEMS], 1):
        lines.append(f"U{i} = {use.fact.span_id}: used in {use.where}: \"{use.sentence}\"")
    if claim_rows:
        facts = [f for f in ledger if f.origin != "claude"][-MAX_ITEMS:]
        lines.append("Ledger facts for judging C items:")
        lines += [f"  {f.span_id}: {_line(f)}" for f in facts]
        lines += [f"{c.span_id}: \"{c.text}\"" for c in claim_rows[:MAX_ITEMS]]
    return "\n".join(lines) + "\n"


def apply_step(store: Store, answer: dict | None, new: list[Span], scan: Scan,
               claim_rows: list[Span], step: int) -> None:
    """Merge the sidecar's judgments into the ledger; anything invalid is ignored."""
    if not isinstance(answer, dict):
        return
    known = {w for ws in lexicon.HEDGES.values() for w in ws}
    by_id = {s.span_id: s for s in new}
    for item in answer.get("facts") or []:
        span = by_id.get(str(item.get("id"))) if isinstance(item, dict) else None
        if span is None:
            continue
        if item.get("critical") is False:
            store.delete_fact(span.span_id)
            continue
        extra = [q.strip().lower() for q in item.get("extra_qualifiers") or [] if isinstance(q, str)]
        extra = [q for q in dict.fromkeys(extra) if q and q in span.text.lower() and q not in known
                 and q not in span.qualifiers.split("; ")]
        if extra:
            store.update_fact(span.span_id,
                              qualifiers="; ".join([*filter(None, span.qualifiers.split("; ")), *extra]))
    claims = {c.span_id: c for c in claim_rows}
    for item in answer.get("claims") or []:
        claim = claims.get(str(item.get("id"))) if isinstance(item, dict) else None
        if claim is None or item.get("origin") not in ORIGINS:
            continue
        hybrid = item["origin"] == "Hybrid"
        store.update_fact(claim.span_id, category=item["origin"],
                          primary_source=str(item.get("primary_source") or "") if hybrid else "",
                          sources_agree=str(item.get("sources_agree") or "") if hybrid else "")
    uses = {f"U{i}": u for i, u in enumerate(scan.uses, 1)}
    for item in answer.get("uses") or []:
        use = uses.get(str(item.get("id"))) if isinstance(item, dict) else None
        impact = str(item.get("impact") or "").strip() if use else ""
        if use and impact:
            store.append_impact(use.fact.span_id, f"step {step}: {impact[:200]}")


def run_step(store: Store, backend, step: int, tool: str, tool_input: str, new: list[Span],
             scan: Scan, claim_rows: list[Span]) -> dict:
    """One sidecar call for this step, if it meets the threshold; returns its usage record."""
    if backend is None or backend.name == "none" or not needs_call(new, scan, claim_rows):
        return {}
    prompt = step_prompt(step, tool, tool_input, new, scan, claim_rows, store.spans())
    apply_step(store, backend.complete_json(prompt, STEP_SCHEMA), new, scan, claim_rows, step)
    return dict(backend.last_usage or {})


def final_prompt(used: list[Span], claims, answer: str) -> str:
    lines = [FINAL_INSTRUCTIONS]
    for f in used[:MAX_ITEMS]:
        lines.append(f"{f.span_id}: {_line(f)}; uses: {f.uses or 'none'}; impact so far: "
                     f"{f.impact or 'none'}")
    lines.append(f"Final answer: {' '.join(answer.split())[:2000]}")
    lines += [f"- [{c.verdict}] {c.text}" for c in claims[:MAX_ITEMS]]
    return "\n".join(lines) + "\n"


def run_final(store: Store, backend, claims, answer: str) -> tuple[str, dict]:
    """At Stop: each used fact's effect on the conclusion, and the report summary (REP-2)."""
    if backend is None or backend.name == "none":
        return "", {}
    cited = {i for c in claims for i in c.span_ids}
    used = [f for f in store.spans() if f.uses or f.span_id in cited]
    if not used:
        return "", {}
    result = backend.complete_json(final_prompt(used, claims, answer), FINAL_SCHEMA)
    summary = ""
    if isinstance(result, dict):
        ids = {f.span_id for f in used}
        for item in result.get("facts") or []:
            if isinstance(item, dict) and item.get("id") in ids and item.get("final_impact"):
                store.append_impact(item["id"], f"conclusion: {str(item['final_impact'])[:200]}")
        summary = str(result.get("summary") or "").strip()
    return summary, dict(backend.last_usage or {})
