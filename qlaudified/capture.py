"""Turn a retrieval tool result into spans (CAP-1, CAP-5, CAP-6).

Retrieval = Read, Grep, WebFetch, WebSearch, MCP tools, and Bash output (simple file reads such as
cat/type/Get-Content/head/tail/sed -n are upgraded to file spans). Read output has its line-number
prefixes stripped; the numbers become the locator. Payload field locations come from the Sprint 0
findings. Sprint 1.
"""

from qlaudified.store import Span


def spans_from_tool_result(payload: dict) -> list[Span]:
    raise NotImplementedError("Sprint 1: CAP-1")
