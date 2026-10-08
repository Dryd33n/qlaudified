"""Turn a retrieval tool result into spans (CAP-1, CAP-5, CAP-6).

Field locations come from the Sprint 0 payload map (docs/findings/sprint-0.md):

- Read: ``tool_response.file.{filePath, content, startLine, numLines}``; content has no line prefixes.
- Grep (content mode): ``tool_response.content`` lines ``rel\\path:line:text``.
- Bash / PowerShell: ``tool_response.stdout``; simple file reads (cat, type, Get-Content, head,
  tail, sed -n) are upgraded to file spans with line ranges.
- WebFetch: the summary in ``result`` (the raw page comes from the Sprint 3 re-fetch).
- WebSearch: ``results[].content[] = {title, url}``.
- MCP (``mcp__<server>__<tool>``): the response is a list of ``{type, text}`` blocks.

Every other tool (Glob, ToolSearch, Agent, ...) is ignored, and nothing under our own store is
ever captured. Subagent calls carry ``agent_id``.
"""

import hashlib
import json
import os
import re
from pathlib import Path

from qlaudified import indexer, paths
from qlaudified.store import Span

SHELL_TOOLS = {"Bash", "PowerShell"}
RETRIEVAL_TOOLS = {"Read", "Grep", "WebFetch", "WebSearch", *SHELL_TOOLS}
CODE_EXTENSIONS = {
    ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".c", ".h", ".cpp",
    ".hpp", ".cs", ".rb", ".php", ".swift", ".scala", ".lua", ".sh", ".ps1", ".sql", ".toml",
    ".yaml", ".yml", ".json", ".ini", ".cfg",
}
MAX_LINES_PER_SPAN = 40
MAX_SPANS_PER_CALL = 200
MAX_OUTPUT_CHARS = 200_000  # bigger command output is skipped (logs, dumps)
INSTALL_COMMAND = re.compile(
    r"^\s*(?:(?:py(?:\s+-3[.\d]*)?|python3?)\s+-m\s+)?"
    r"(pip3?|npm|pnpm|yarn|brew|apt(-get)?|choco|winget|conda|uv)\b.*\b(install|add|upgrade|update)\b",
    re.IGNORECASE,
)
_ARG = r"(?P<file>\"[^\"]+\"|'[^']+'|[^\s|;&<>]+)"
FILE_READS = [
    (re.compile(r"^\s*(?:cat|type|Get-Content|gc)\s+" + _ARG + r"\s*$", re.IGNORECASE), "all"),
    (re.compile(r"^\s*head\s+(?:-n\s*|-)(?P<n>\d+)\s+" + _ARG + r"\s*$"), "head"),
    (re.compile(r"^\s*tail\s+(?:-n\s*|-)(?P<n>\d+)\s+" + _ARG + r"\s*$"), "tail"),
    (re.compile(r"^\s*sed\s+-n\s+['\"]?(?P<a>\d+),(?P<b>\d+)p['\"]?\s+" + _ARG + r"\s*$"), "sed"),
]
_GREP_LINE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):(?P<text>.*)$")


def is_retrieval(tool_name: str) -> bool:
    return tool_name in RETRIEVAL_TOOLS or tool_name.startswith("mcp__")


def spans_from_tool_result(
    payload: dict, project: Path | None = None, lexicon: dict[str, list[str]] | None = None
) -> list[Span]:
    """Spans for one PostToolUse payload, indexed and ready to store (IDs are set by the store)."""
    tool = payload.get("tool_name") or ""
    if not is_retrieval(tool):
        return []
    project = project if project is not None else paths.project_dir(payload)
    cwd = payload.get("cwd")
    tool_input = payload.get("tool_input") or {}
    response = payload.get("tool_response")

    if tool == "Read":
        raw = _read_spans(response, project, cwd)
    elif tool == "Grep":
        raw = _grep_spans(response, project, cwd)
    elif tool in SHELL_TOOLS:
        raw = _shell_spans(tool_input, response, project, cwd)
    elif tool == "WebFetch":
        raw = _webfetch_spans(tool_input, response)
    elif tool == "WebSearch":
        raw = _websearch_spans(response)
    else:
        raw = _mcp_spans(tool, response)

    agent = payload.get("agent_id") or "main"
    turn = payload.get("prompt_id")
    out = []
    for origin, source, locator, text in raw[:MAX_SPANS_PER_CALL]:
        if not text.strip() or paths.is_store_path(source):
            continue
        hedges = indexer.find_hedges(text, lexicon)
        out.append(Span(
            span_id="", origin=origin, source=source, locator=locator, text=text,
            numbers="; ".join(indexer.extract_numbers(text) + indexer.extract_dates(text)),
            qualifiers="; ".join(w for words in hedges.values() for w in words),
            agent_id=agent, turn=turn,
            hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        ))
    return out


RawSpan = tuple[str, str, str, str]  # origin, source, locator, text


def _origin_for(source: str) -> str:
    return "code" if os.path.splitext(source)[1].lower() in CODE_EXTENSIONS else "local-doc"


def _locator(first: int, last: int) -> str:
    return f"L{first}" if first == last else f"L{first}-L{last}"


def _chunks(text: str, start_line: int) -> list[tuple[int, int, str]]:
    """Split file text at blank lines into passages of at most MAX_LINES_PER_SPAN lines."""
    out: list[tuple[int, int, str]] = []
    block: list[str] = []
    first = start_line
    for n, line in enumerate(text.splitlines(), start_line):
        if line.strip() and len(block) < MAX_LINES_PER_SPAN:
            if not block:
                first = n
            block.append(line)
            continue
        if block:
            out.append((first, first + len(block) - 1, "\n".join(block)))
        block, first = ([line] if line.strip() else []), n
    if block:
        out.append((first, first + len(block) - 1, "\n".join(block)))
    return out


_SENTENCE_END = re.compile(r"[.!?:;)\]\"']\s*$")


def _file_spans(source: str, text: str, start_line: int) -> list[RawSpan]:
    """Code: one span per blank-line block. Prose: also one span per line when every line of a
    block is a full sentence (notes written one fact per line), so each fact keeps its own line."""
    origin = _origin_for(source)
    out: list[RawSpan] = []
    for a, b, chunk in _chunks(text, start_line):
        lines = chunk.splitlines()
        if origin == "local-doc" and len(lines) > 1 and all(_SENTENCE_END.search(ln) for ln in lines):
            out += [(origin, source, _locator(n, n), ln) for n, ln in enumerate(lines, a)]
        else:
            out.append((origin, source, _locator(a, b), chunk))
    return out


def _read_spans(response, project: Path, cwd: str | None) -> list[RawSpan]:
    file = (response or {}).get("file") if isinstance(response, dict) else None
    if not isinstance(file, dict) or not isinstance(file.get("content"), str):
        return []
    source = paths.normalize(file.get("filePath") or "", project, cwd)
    return _file_spans(source, file["content"], int(file.get("startLine") or 1))


def _grep_spans(response, project: Path, cwd: str | None) -> list[RawSpan]:
    content = response.get("content") if isinstance(response, dict) else None
    if not isinstance(content, str):
        return []  # files_with_matches and count modes carry no text
    out: list[RawSpan] = []
    for line in content.splitlines():
        m = _GREP_LINE.match(line)
        if not m or m["text"].strip() == "[Omitted long matching line]":
            continue
        source = paths.normalize(m["path"], project, cwd)
        n = int(m["line"])
        out.append((_origin_for(source), source, _locator(n, n), m["text"]))
    return out


def _shell_output(response) -> str:
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return ""
    for key in ("stdout", "output", "content"):
        if isinstance(response.get(key), str) and response[key].strip():
            return response[key]
    return response.get("stderr") or ""


def _shell_spans(tool_input: dict, response, project: Path, cwd: str | None) -> list[RawSpan]:
    command = str(tool_input.get("command") or "").strip()
    output = _shell_output(response)
    if not output.strip() or len(output) > MAX_OUTPUT_CHARS or INSTALL_COMMAND.match(command):
        return []
    for pattern, kind in FILE_READS:
        m = pattern.match(command)
        if not m:
            continue
        source = paths.normalize(m["file"].strip("\"'"), project, cwd)
        start = 1
        if kind == "sed":
            start = int(m["a"])
        elif kind == "tail":
            total = _line_count(Path(cwd or project) / m["file"].strip("\"'"))
            if total is None:
                break  # unknown start line: keep it as command output
            start = max(1, total - int(m["n"]) + 1)
        return _file_spans(source, output, start)
    source = "$ " + command[:200]
    return [("command-output", source, f"p{i}", chunk)
            for i, (_, _, chunk) in enumerate(_chunks(output, 1), 1)]


def _line_count(path: Path) -> int | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return None


# Claude Code appends this to long pages; it describes the fetch, not the page.
_WEBFETCH_NOTE = re.compile(r"\s*\[WebFetch note:.*?\]\s*$", re.DOTALL)


def _webfetch_spans(tool_input: dict, response) -> list[RawSpan]:
    if not isinstance(response, dict) or not isinstance(response.get("result"), str):
        return []
    url = response.get("url") or tool_input.get("url") or ""
    return [("web-summary", url, "summary", _WEBFETCH_NOTE.sub("", response["result"]))]


def _websearch_spans(response) -> list[RawSpan]:
    results = response.get("results") if isinstance(response, dict) else None
    out: list[RawSpan] = []
    for result in results if isinstance(results, list) else []:
        items = result.get("content") if isinstance(result, dict) else None
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("url"):
                out.append(("search-snippet", item["url"], "title", str(item.get("title") or "")))
    return out


def _mcp_spans(tool: str, response) -> list[RawSpan]:
    blocks = response.get("content") if isinstance(response, dict) else response
    if isinstance(blocks, str):
        text = blocks
    elif isinstance(blocks, list):
        text = "\n\n".join(
            b["text"] for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str)
        )
    else:
        text = json.dumps(response) if response else ""
    _, server, name = (tool.split("__", 2) + ["", ""])[:3]
    source = f"mcp:{server}/{name}"
    return [("mcp", source, f"p{i}", chunk) for i, (_, _, chunk) in enumerate(_chunks(text, 1), 1)]
