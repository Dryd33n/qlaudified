"""Distance and re-reads from a run's session transcript (study v2; methods critique, fix 5).

Every assistant message in a Claude Code transcript carries ``usage``; input plus cached tokens is
the context size at that point. **Distance** is the context size at the final answer minus the
context size just after the last read of a source document: the tokens of distractor reading and
conversation the hedged fact had to survive. **Re-read** is whether Claude opened a source again
after the final question, which shortens the distance to nothing (allowed, but reported).
"""

import json
from pathlib import Path


def _context(usage: dict) -> int:
    return sum(usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                           "cache_read_input_tokens"))


def _reads_source(block: dict, sources: set[str]) -> bool:
    if block.get("type") != "tool_use":
        return False
    text = json.dumps(block.get("input") or {}).replace("\\\\", "/").replace("\\", "/")
    return any(name in text for name in sources)


def measure(path: Path, sources: list[str]) -> dict:
    """``{"distance_tokens": int | None, "reread": bool, "final_context": int | None}``."""
    names = set(sources)
    lines = [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    last_prompt = max((i for i, r in enumerate(lines) if r.get("type") == "user"
                       and isinstance((r.get("message") or {}).get("content"), str)), default=-1)
    contexts: list[tuple[int, int]] = []  # (line index, context size) of assistant messages
    last_read = None
    reread = False
    final_context = None
    for i, rec in enumerate(lines):
        msg = rec.get("message") or {}
        if rec.get("type") != "assistant":
            continue
        contexts.append((i, _context(msg.get("usage") or {})))
        content = msg.get("content")
        blocks: list = content if isinstance(content, list) else []
        if any(_reads_source(b, names) for b in blocks):
            last_read = i
            reread = reread or i > last_prompt
        if any(b.get("type") == "text" and b.get("text", "").strip() for b in blocks):
            final_context = contexts[-1][1]
    after_read = next((c for i, c in contexts if last_read is not None and i > last_read), None)
    distance = (final_context - after_read) if final_context is not None and after_read is not None \
        else None
    return {"distance_tokens": distance, "reread": reread, "final_context": final_context}
