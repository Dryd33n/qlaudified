"""Time a hook end to end, exactly as Claude Code runs it (NFR-3: PostToolUse p95 <= 300 ms).

    py -3 scripts/bench_capture.py [--runs 30] [--fixture post_read] [--event PostToolUse]
                                   [--prime post_read] [--text "..."] [--target 300]

Other events use the same command line with the event name swapped. ``--prime`` first runs that
PostToolUse fixture into the same session, so MessageDisplay and Stop have spans to match; ``--text``
sets the MessageDisplay ``delta`` or the Stop ``last_assistant_message``.

Runs the real hooks.json command through bash (shell form, py -3 / python3 fallback) on a recorded
payload into a temp project, so the time includes shell and interpreter startup, capture and the
SQLite write. Results are appended to docs/findings/data/capture_latency.jsonl.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from qlaudified.testing.sim import placeholders, substitute


def git_bash() -> str:
    """The bash Claude Code uses on Windows. PATH may find WSL's bash.exe first, which is wrong."""
    for candidate in (os.environ.get("CLAUDE_CODE_GIT_BASH_PATH"),
                      r"C:\Program Files\Git\bin\bash.exe"):
        if candidate and os.path.exists(candidate):
            return candidate
    git = shutil.which("git")
    if git:
        guess = Path(git).resolve().parent.parent / "bin" / "bash.exe"
        if guess.exists():
            return str(guess)
    raise SystemExit("Git Bash not found; set CLAUDE_CODE_GIT_BASH_PATH")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--fixture", default="post_read")
    parser.add_argument("--event", default="PostToolUse")
    parser.add_argument("--prime", help="PostToolUse fixture to store first, in the same session")
    parser.add_argument("--text", help="MessageDisplay delta or Stop answer")
    parser.add_argument("--target", type=float, default=300, help="p95 target in ms")
    args = parser.parse_args()

    hooks = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    command = hooks["hooks"]["PostToolUse"][0]["hooks"][0]["command"].replace(
        "PostToolUse", args.event)
    bash = git_bash() if sys.platform == "win32" else (shutil.which("bash") or "bash")
    workdir = Path(tempfile.mkdtemp(prefix="qlaudified-bench-"))
    try:
        template = json.loads((REPO / "tests" / "fixtures" / "payloads" / f"{args.fixture}.json")
                              .read_text(encoding="utf-8"))
        payload = substitute(template, placeholders(workdir))
        project = workdir / "sandbox"
        project.mkdir(parents=True)
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project), "CLAUDE_PLUGIN_ROOT": str(REPO)}
        if args.prime:
            primer = substitute(json.loads((REPO / "tests" / "fixtures" / "payloads" /
                                            f"{args.prime}.json").read_text(encoding="utf-8")),
                                placeholders(workdir))
            primer.update(session_id=payload["session_id"], cwd=payload["cwd"])
            subprocess.run([bash, "-c", command.replace(args.event, "PostToolUse")],
                           input=json.dumps(primer).encode(), env=env, check=True)
        if args.text is not None:
            payload["delta" if args.event == "MessageDisplay" else "last_assistant_message"] = args.text
        times = []
        for i in range(args.runs):
            if args.event == "PostToolUse":
                payload["tool_use_id"] = f"bench-{i}"
                payload["agent_id"] = f"bench-{i}"  # a new span every run, never a dedupe hit
            start = time.perf_counter()
            proc = subprocess.run([bash, "-c", command], input=json.dumps(payload).encode(),
                                  env=env, capture_output=True, check=False, timeout=60)
            times.append((time.perf_counter() - start) * 1000)
            if proc.returncode != 0:
                print(proc.stderr.decode(errors="replace"))
                return 1
        errors = project / ".claude" / ".qlaudified" / "errors.log"
        if errors.exists():
            print(errors.read_text(encoding="utf-8"))
            return 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    times.sort()
    result = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "os": platform.platform(),
        "python": platform.python_version(), "event": args.event, "fixture": args.fixture,
        "prime": args.prime, "text_chars": len(args.text or ""), "runs": args.runs,
        "p50_ms": round(times[len(times) // 2], 1),
        "p95_ms": round(times[min(len(times) - 1, int(0.95 * len(times)))], 1),
        "max_ms": round(times[-1], 1),
    }
    out = REPO / "docs" / "findings" / "data" / "capture_latency.jsonl"
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")
    print(json.dumps(result))
    return 0 if result["p95_ms"] <= args.target else 2


if __name__ == "__main__":
    sys.exit(main())
