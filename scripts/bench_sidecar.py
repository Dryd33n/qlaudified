"""Sidecar step cost and latency (NFR-4: p95 <= 10 s per step that meets the threshold).

    py -3 scripts/bench_sidecar.py [--sessions seed-hedged-windows ...] [--mode medium] [--live]

Replays the recorded sessions in tests/sessions through the PostToolUse and Stop handlers in
process, with a fake backend that answers every ID in the prompt, so the Administrator's merge
code runs too. Per session it counts tool steps and the steps that met the threshold (PROV-6), and
records each sidecar prompt's size and the handler time around the call (prompt building, merge,
CSV rewrite; no model).

``--live`` then sends the median-sized step prompt once to the configured claude-cli backend
(haiku): one call, its wall time, tokens and cost. The NFR-4 estimate is the rule path p95 (from
bench_capture.py) + the fake-backend handler p95 + the live call's wall time.

Results are appended to docs/findings/data/sidecar.jsonl.
"""

import argparse
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from qlaudified import administrator, backends
from qlaudified.testing.sim import placeholders, substitute

HANDLERS = {"PostToolUse": "post_tool_use", "Stop": "stop", "UserPromptSubmit": "user_prompt_submit",
            "SessionStart": "session_start"}


class BenchBackend:
    """Answers every F, C and U ID in a step prompt, and every fact in a final prompt."""

    name = "bench-fake"
    model = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.last_usage: dict = {}

    def complete_json(self, prompt: str, schema: dict) -> dict | None:
        kind = "step" if schema is administrator.STEP_SCHEMA else (
            "final" if schema is administrator.FINAL_SCHEMA else "verify")
        self.calls.append({"kind": kind, "prompt": prompt})
        self.last_usage = {"wall_ms": 0}
        if kind == "final":
            ids = re.findall(r"^(F\d+): ", prompt, re.MULTILINE)
            return {"facts": [{"id": i, "final_impact": "supports the answer"} for i in ids],
                    "summary": "The answer rests on the ledger's facts."}
        if kind != "step":
            return None
        head, _, ledger = prompt.partition("Ledger facts for judging C items:")
        facts = re.findall(r"^(F\d+): ", head, re.MULTILINE)
        claims = re.findall(r"^(F\d+): \"", ledger, re.MULTILINE)
        uses = re.findall(r"^(U\d+) = ", prompt, re.MULTILINE)
        return {"facts": [{"id": i, "critical": True, "extra_qualifiers": []} for i in facts],
                "claims": [{"id": i, "origin": "Model Inference", "primary_source": "",
                            "sources_agree": ""} for i in claims],
                "uses": [{"id": i, "impact": "fed this step"} for i in uses]}


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 1) if xs else 0.0


def replay(session: Path, mode: str, backend: BenchBackend) -> dict:
    """Run one recorded session through the handlers in process; time each sidecar step."""
    import importlib

    workdir = Path(tempfile.mkdtemp(prefix="qlaudified-sidecar-"))
    try:
        mapping = placeholders(workdir)
        sandbox = workdir / "sandbox"
        if (session / "sandbox").is_dir():
            shutil.copytree(session / "sandbox", sandbox, dirs_exist_ok=True)
        sandbox.mkdir(parents=True, exist_ok=True)
        records = [json.loads(line) for line in
                   (session / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        first = next((r["payload"] for r in records if isinstance(r.get("payload"), dict)), {})
        project = Path(substitute(first.get("cwd") or "<SANDBOX>", mapping))
        store = project / ".claude" / ".qlaudified"
        store.mkdir(parents=True, exist_ok=True)
        (store / "config.toml").write_text(f'mode = "{mode}"\n', encoding="utf-8")
        os.environ.update(CLAUDE_PROJECT_DIR=str(project), CLAUDE_PLUGIN_ROOT=str(REPO),
                          QLAUDIFIED_OFFLINE="1")  # no re-fetch; the backend is patched below

        steps = qualifying = 0
        step_ms: list[float] = []
        for rec in records:
            module = HANDLERS.get(rec["event"])
            payload = substitute(rec.get("payload"), mapping)
            if module is None or not isinstance(payload, dict):
                continue
            before = len(backend.calls)
            start = time.perf_counter()
            importlib.import_module(f"qlaudified.hooks.{module}").handle(payload)
            elapsed = (time.perf_counter() - start) * 1000
            if rec["event"] == "PostToolUse":
                steps += 1
                if any(c["kind"] == "step" for c in backend.calls[before:]):
                    qualifying += 1
                    step_ms.append(elapsed)
        return {"session": session.name, "steps": steps, "qualifying": qualifying,
                "step_ms": step_ms}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", nargs="*", help="names under tests/sessions (default: all)")
    parser.add_argument("--mode", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--live", action="store_true",
                        help="send the median step prompt once to claude-cli (uses plan usage)")
    args = parser.parse_args()

    root = REPO / "tests" / "sessions"
    sessions = [root / n for n in args.sessions] if args.sessions else sorted(
        p for p in root.iterdir() if (p / "events.jsonl").exists())
    backend = BenchBackend()
    backends.get_backend = lambda *_a, **_k: backend  # the hooks import it at call time

    per_session = [replay(s, args.mode, backend) for s in sessions]
    step_prompts = [c["prompt"] for c in backend.calls if c["kind"] == "step"]
    final_prompts = [c["prompt"] for c in backend.calls if c["kind"] == "final"]
    step_ms = [ms for r in per_session for ms in r["step_ms"]]
    steps = sum(r["steps"] for r in per_session)
    qualifying = sum(r["qualifying"] for r in per_session)
    chars = [len(p) for p in step_prompts]
    result: dict = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "os": platform.platform(),
        "python": platform.python_version(), "mode": args.mode, "sessions": len(sessions),
        "steps": steps, "qualifying_steps": qualifying,
        "qualifying_share": round(qualifying / steps, 3) if steps else 0.0,
        "step_calls": len(step_prompts), "final_calls": len(final_prompts),
        "step_prompt_chars_p50": pct(chars, 0.5), "step_prompt_chars_p95": pct(chars, 0.95),
        "step_prompt_chars_max": max(chars, default=0),
        "final_prompt_chars_p50": pct([len(p) for p in final_prompts], 0.5),
        "fake_step_ms_p50": pct(step_ms, 0.5), "fake_step_ms_p95": pct(step_ms, 0.95),
        "per_session": [{k: v for k, v in r.items() if k != "step_ms"} for r in per_session],
    }

    if args.live and step_prompts:
        from qlaudified.backends.claude_cli import ClaudeCliBackend

        median = sorted(step_prompts, key=len)[len(step_prompts) // 2]
        os.environ.pop("QLAUDIFIED_OFFLINE", None)
        live = ClaudeCliBackend("haiku")
        answer = live.complete_json(median, administrator.STEP_SCHEMA)
        result["live"] = {"prompt_chars": len(median), "answered": isinstance(answer, dict),
                          **live.last_usage}

    out = REPO / "docs" / "findings" / "data" / "sidecar.jsonl"
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
