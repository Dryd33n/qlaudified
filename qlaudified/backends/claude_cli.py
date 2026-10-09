"""``claude -p --safe-mode`` with a JSON schema (CFG-1, SID-3).

``--safe-mode`` loads no hooks, plugins, skills or CLAUDE.md, so the nested call can't recurse
into qlaudified; ``QLAUDIFIED_NESTED=1`` makes hooks/run.py exit at once as a second guard. The
call gets no tools, isn't saved as a session, and runs in the temp folder, away from the project.
Sprint 3 probe: ~3.3 s and ~$0.0008 for one small haiku call; the answer is in ``structured_output``.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time

TIMEOUT_S = 120


class ClaudeCliBackend:
    name = "claude-cli"

    def __init__(self, model: str) -> None:
        self.model = model
        self.last_usage: dict = {}

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        exe = shutil.which("claude")
        if not exe:
            self.last_usage = {"error": "claude not found on PATH"}
            return None
        cmd = [exe, "-p", "--safe-mode", "--model", self.model, "--output-format", "json",
               "--tools", "", "--no-session-persistence", "--json-schema", json.dumps(schema)]
        env = {**os.environ, "QLAUDIFIED_NESTED": "1"}
        start = time.perf_counter()
        try:
            proc = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True,
                                  env=env, cwd=tempfile.gettempdir(), timeout=TIMEOUT_S,
                                  check=False)
            data = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
        except (OSError, subprocess.TimeoutExpired, ValueError) as e:
            self.last_usage = {"error": f"{type(e).__name__}: {e}"[:300],
                               "wall_ms": round((time.perf_counter() - start) * 1000)}
            return None
        usage = data.get("usage") or {}
        self.last_usage = {
            "wall_ms": round((time.perf_counter() - start) * 1000),
            "cost_usd": data.get("total_cost_usd"),
            "input_tokens": sum(usage.get(k) or 0 for k in (
                "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
            "output_tokens": usage.get("output_tokens"),
            "returncode": proc.returncode,
        }
        out = data.get("structured_output")
        if data.get("is_error") or not isinstance(out, dict):
            self.last_usage["error"] = str(data.get("result") or proc.stderr[-300:])[:300]
            return None
        return out
