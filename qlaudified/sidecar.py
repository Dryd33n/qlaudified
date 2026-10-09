"""High-mode in-loop sidecar on flagged sentences only (SID-1, SID-2).

PostToolUse in High sends the new spans' flagged sentences (a number, date, hedge or named entity;
never whole documents) to a small model in a detached job (background.py). The model rates each
sentence's criticality and lists the qualifiers the lexicon missed ("unaudited", "as of the
draft"). Only qualifiers that appear verbatim in the sentence are kept. Results go to the
``sidecar`` table: the next PostToolUse injects them for that agent, and Stop adds them to the
lexicon so a claim that drops one is flagged like any other dropped qualifier.
"""

import re
import sys

from qlaudified import indexer, lexicon, text
from qlaudified.store import Span

MAX_SENTENCES = 30
_ENTITY = re.compile(r"(?<!^)\b[A-Z][a-z]+\b")

SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "criticality": {"type": "number"},
                    "qualifiers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "criticality", "qualifiers"],
            },
        },
    },
    "required": ["sentences"],
}

INSTRUCTIONS = """\
Each line below is a sentence from a document an AI assistant just read. For each sentence:
- criticality: 0 to 1, how much it matters that a summary keeps this sentence's facts exact
  (numbers, dates, names and their conditions matter most).
- qualifiers: words or phrases in the sentence that make what it asserts less certain or
  conditional: uncertainty, estimates, conditions ("if", "unless"), attribution, provisional or
  unverified status ("unaudited", "in beta"). Never ordinary verbs, prepositions or descriptions
  ("is", "due on", "grew to", "per month"). Copy them exactly as they appear. Leave out common
  hedges already listed here: {known}. Most sentences have none: return [].
Answer for every sentence ID.
"""


def flag_sentences(spans: list[Span]) -> list[tuple[str, Span, str]]:
    """(id, span, sentence) for sentences with a number, date, hedge or named entity (SID-1)."""
    out: list[tuple[str, Span, str]] = []
    for span in spans:
        if span.origin == "search-snippet":
            continue
        for sentence in text.units(span.text):
            cleaned = text.clean(sentence)
            if len(cleaned.split()) < 4:
                continue
            if text.numbers(cleaned) or indexer.find_hedges(cleaned) or _ENTITY.search(cleaned):
                out.append((f"F{len(out) + 1}", span, sentence))
                if len(out) == MAX_SENTENCES:
                    return out
    return out


def build_prompt(flagged: list[tuple[str, Span, str]]) -> str:
    known = ", ".join(sorted({w for words in lexicon.HEDGES.values() for w in words}))
    lines = [INSTRUCTIONS.format(known=known)]
    lines += [f"{fid}: {' '.join(sentence.split())}" for fid, _, sentence in flagged]
    return "\n".join(lines) + "\n"


def classify(flagged: list[tuple[str, Span, str]], backend) -> list[dict]:
    """One call for all flagged sentences (SID-2); rows for the sidecar table."""
    if not flagged:
        return []
    answer = backend.complete_json(build_prompt(flagged), SCHEMA)
    items = answer.get("sentences") if isinstance(answer, dict) else None
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)} if isinstance(items, list) else {}
    known = {w for words in lexicon.HEDGES.values() for w in words}
    rows = []
    for fid, span, sentence in flagged:
        item = by_id.get(fid)
        if not item:
            continue
        low = sentence.lower()
        qualifiers = [q.strip().lower() for q in item.get("qualifiers") or [] if isinstance(q, str)]
        # Verbatim only: a qualifier the sentence doesn't contain is the model's invention.
        qualifiers = [q for q in dict.fromkeys(qualifiers) if q and q in low and q not in known]
        try:
            criticality = max(0.0, min(1.0, float(item.get("criticality", 0.5))))
        except (TypeError, ValueError):
            criticality = 0.5
        rows.append({"span_id": span.span_id, "sentence": sentence, "criticality": criticality,
                     "qualifiers": qualifiers, "agent_id": span.agent_id})
    return rows


def start(session_dir, project, spans: list[Span]) -> None:
    """Launch the sidecar on these spans in the background, if any sentence is flagged."""
    from qlaudified import background

    if not flag_sentences(spans):
        return
    background.launch(session_dir, "qlaudified.sidecar", f"sidecar-{spans[0].span_id}", {
        "project": str(project), "span_ids": [s.span_id for s in spans]})


def run(job: dict) -> int:
    from qlaudified import config
    from qlaudified.backends import get_backend
    from qlaudified.store import Store
    from qlaudified.verify import log_usage

    cfg = config.load(job["project"])
    backend = get_backend(cfg.backend, cfg.backend_model)
    store = Store(job["session_dir"])
    wanted = set(job["span_ids"])
    flagged = flag_sentences([s for s in store.spans() if s.span_id in wanted])
    rows = classify(flagged, backend)
    store.add_sidecar(rows)
    if backend.last_usage:
        log_usage(store.session_dir, {"tier": "sidecar", "backend": backend.name,
                                      "model": getattr(backend, "model", ""),
                                      "sentences": len(flagged), **backend.last_usage})
    return len(rows)


def format_lines(rows: list[dict]) -> list[str]:
    """Injection lines for qualifiers the sidecar found, in the delta's plain-fact format."""
    return [f"[{r['span_id']}] source also qualifies: {', '.join(r['qualifiers'])} "
            f"(\"{' '.join(r['sentence'].split())[:80]}\")" for r in rows]


if __name__ == "__main__":
    from qlaudified.background import run_job

    sys.exit(run_job(sys.argv[1:], run, "Sidecar"))
