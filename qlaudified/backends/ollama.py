"""Local Ollama HTTP API backend (CFG-1): ``/api/chat`` with ``format`` set to the JSON schema.

Nothing leaves the machine (NFR-8). The model is ``backend_model`` in config.toml (e.g.
``qwen2.5:7b``); a missing server or model gives None, so claims stay ``unresolved``.
"""

import json
import time
import urllib.error
import urllib.request

TIMEOUT_S = 120


class OllamaBackend:
    name = "ollama"

    def __init__(self, model: str, url: str = "http://localhost:11434") -> None:
        self.model = model
        self.url = url.rstrip("/")
        self.last_usage: dict = {}

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        body = json.dumps({
            "model": self.model, "stream": False, "format": schema,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0},
        }).encode("utf-8")
        request = urllib.request.Request(f"{self.url}/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                data = json.loads(response.read().decode("utf-8"))
            out = json.loads(data["message"]["content"])
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError) as e:
            self.last_usage = {"error": f"{type(e).__name__}: {e}"[:300],
                               "wall_ms": round((time.perf_counter() - start) * 1000)}
            return None
        self.last_usage = {
            "wall_ms": round((time.perf_counter() - start) * 1000), "cost_usd": 0.0,
            "input_tokens": data.get("prompt_eval_count"), "output_tokens": data.get("eval_count"),
        }
        return out if isinstance(out, dict) else None
