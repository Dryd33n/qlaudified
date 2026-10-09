"""Claude's reasoning between tool calls, read from the session transcript (INT-2).

Hook payloads carry the tool call but not what Claude wrote around it; every payload has
``transcript_path``. The transcript is JSON lines, one content block per assistant line. The
reasoning for a tool call is the assistant text (and thinking, when not redacted) written after
the previous user line (the prompt or a tool result) and before that call. In ``claude -p`` runs
thinking blocks arrive empty (Sprint 5), so this is mostly Claude's visible text.
"""

import json
from pathlib import Path

TAIL_BYTES = 400_000  # only the end of a long transcript matters
MAX_CHARS = 1500


def _lines(path: Path) -> list[dict]:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            raw = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    for line in raw.splitlines()[1 if size > TAIL_BYTES else 0:]:  # first may be cut mid-line
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _blocks(entry: dict) -> list[dict]:
    content = (entry.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def reasoning_before(transcript_path: str | None, tool_use_id: str | None,
                     max_chars: int = MAX_CHARS) -> str:
    """Assistant text written since the last user line and before ``tool_use_id``; "" if unknown."""
    if not transcript_path or not tool_use_id:
        return ""
    lines = _lines(Path(transcript_path))
    end = next((i for i, e in enumerate(lines) if e.get("type") == "assistant" and any(
        b.get("type") == "tool_use" and b.get("id") == tool_use_id for b in _blocks(e))), None)
    if end is None:
        return ""
    texts: list[str] = []
    for entry in reversed(lines[:end]):
        if entry.get("type") == "user":
            break
        if entry.get("type") != "assistant":
            continue
        for block in reversed(_blocks(entry)):
            value = block.get("text") if block.get("type") == "text" else (
                block.get("thinking") if block.get("type") == "thinking" else None)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    text = "\n".join(reversed(texts))
    return text[-max_chars:]
