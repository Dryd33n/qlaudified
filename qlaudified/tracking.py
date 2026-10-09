"""Use tracking (INT-3, PROV-4): where Claude reuses a tracked fact, and what Claude states itself.

Each step, Claude's reasoning since the last step and the tool call's input are scanned:

- a sentence that states a tracked fact's value (same number or date, on the same topic) is a
  **use** of that fact; the first use keeps the qualifiers present in that sentence, which is how
  decay is seen step by step;
- a critical sentence in Claude's reasoning or in a file it writes that matches no tracked fact
  is **Claude's own claim** (Model Inference, Training Data or Hybrid, for the sidecar to judge).
"""

import json
import re

from qlaudified import indexer, paths, text, transcript
from qlaudified.records import record
from qlaudified.store import Span

MIN_TOPIC = 0.25  # share of the fact's words a using sentence must share, unless it's tiny
WORD_USE = 0.6  # facts with no number: share of their words that makes a sentence a use
PROSE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
# Paths and IDs carry digits that aren't facts (tmp6cqrmw/q3.md, toolu_01...).
_CLAUSES = re.compile(r"[,;:]\s+|\s+(?:and|but|while|whereas)\s+")
_PATHS = re.compile(r"\S*[/\\]\S*|\b\w*_\w*\d\w*\b")


@record
class Use:
    fact: Span
    sentence: str
    where: str
    qualifiers: str  # hedge words in the using sentence ("" if none)


@record
class Scan:
    uses: list[Use]
    # (sentence, where, figures): Claude's own critical statements, with the figures in them
    # that match no tracked fact
    claims: list[tuple[str, str, list[str]]]
    reasoning: str


def pieces(payload: dict, project) -> list[tuple[str, str, bool]]:
    """(where, text, prose) for this step: the reasoning, then the tool input."""
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    out = []
    reasoning = transcript.reasoning_before(payload.get("transcript_path"), payload.get("tool_use_id"))
    if reasoning:
        out.append(("reasoning", reasoning, True))
    target = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
    name = paths.normalize(str(target), project, payload.get("cwd")) if target else ""
    if tool == "Write":
        out.append((f"Write {name}", str(ti.get("content") or ""), True))
    elif tool == "Edit":
        out.append((f"Edit {name}", str(ti.get("new_string") or ""), True))
    elif tool == "MultiEdit":
        joined = "\n".join(str(e.get("new_string") or "") for e in ti.get("edits") or []
                           if isinstance(e, dict))
        out.append((f"Edit {name}", joined, True))
    elif tool in ("Bash", "PowerShell"):
        command = str(ti.get("command") or "")
        out.append((f"{tool} {' '.join(command.split())[:40]}", command, False))
    elif tool in ("Agent", "Task"):
        out.append((f"{tool} prompt", str(ti.get("prompt") or ""), True))
    elif ti:
        out.append((tool, json.dumps(ti)[:2000], False))
    return [(w, t, p) for w, t, p in out if t.strip()]


def _topic(fact_tokens: set[str], tokens: set[str]) -> float:
    """Shared topic words (numbers excluded), the better of both directions."""
    a, b = text.words(fact_tokens), text.words(tokens)
    return max(text.coverage(a, b), text.coverage(b, a))


def scan(facts: list[Span], step: int, parts: list[tuple[str, str, bool]],
         lexicon: dict[str, list[str]] | None = None) -> Scan:
    """Find uses of earlier facts and Claude's own critical claims in this step's text."""
    earlier = [f for f in facts if f.step < step and f.origin != "claude"]
    with_numbers = [(f, text.split_numbers(f.numbers), set(text.tokens(text.clean(f.text))))
                    for f in earlier if f.numbers]
    words_only = [(f, set(text.tokens(text.clean(f.text)))) for f in earlier if not f.numbers]
    uses: list[Use] = []
    claims: list[tuple[str, str, list[str]]] = []
    reasoning = next((t for w, t, _ in parts if w == "reasoning"), "")
    for where, body, prose in parts:
        for line in body.splitlines():
            for sentence in text.sentences(line.strip()):
                tokens = set(text.tokens(_PATHS.sub(" ", text.clean(sentence))))
                own: list[str] = []  # numbers in this sentence that match no tracked fact
                matched_any = False
                # A hedge belongs to the figure in its own clause: in "revenue was $4.2M, so per
                # head that's about $87.5K", "about" qualifies the $87.5K, not the $4.2M.
                for clause in _CLAUSES.split(sentence):
                    nums = text.numbers(_PATHS.sub(" ", text.clean(clause)))
                    hedges = indexer.find_hedges(clause, lexicon)
                    quals = "; ".join(w for ws in hedges.values() for w in ws)
                    for n in nums:
                        hits = [fact for fact, fact_nums, fact_tokens in with_numbers
                                if any(text.number_match(n, m) for m in fact_nums)
                                and (len(text.words(tokens)) <= 2 or
                                     _topic(fact_tokens, tokens) >= MIN_TOPIC)]
                        for fact in hits:
                            if not any(u.fact is fact and u.where == where for u in uses):
                                uses.append(Use(fact, sentence, where, quals))
                        matched_any |= bool(hits)
                        if not hits:
                            own.append(n)
                if not own and not matched_any and prose:
                    hedges = indexer.find_hedges(sentence, lexicon)
                    quals = "; ".join(w for ws in hedges.values() for w in ws)
                    for fact, fact_tokens in words_only:
                        if len(fact_tokens) >= 3 and text.coverage(fact_tokens, tokens) >= WORD_USE:
                            uses.append(Use(fact, sentence, where, quals))
                if prose and own and len(sentence.split()) >= 3:
                    claims.append((sentence, where, own))
    return Scan(uses, claims, reasoning)


def claim_rows(claims: list[tuple[str, str, list[str]]], step: int, agent: str, turn: str | None,
               lexicon: dict[str, list[str]] | None = None) -> list[Span]:
    """Rows for Claude's own critical statements; the sidecar classifies their origin."""
    from qlaudified.capture import _hash

    out = []
    for sentence, where, figures in claims:
        hedges = indexer.find_hedges(sentence, lexicon)
        out.append(Span(
            span_id="", origin="claude", source="claude", locator=f"step {step}", text=sentence,
            numbers="; ".join(figures),
            qualifiers="; ".join(w for ws in hedges.values() for w in ws),
            agent_id=agent, turn=turn, hash=_hash(sentence), category="Unclassified", step=step,
            uses=f"{step}:{where}",
        ))
    return out
