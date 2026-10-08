"""Run one live task in an isolated `claude -p` session with a plugin under test (testing.md).

    python scripts/live.py <task> [--plugin-dir DIR | --no-plugin] [--model haiku] [--max-turns 6] [--dry-run]

<task> names tests/sandbox/<task>/, which holds the sandbox files and a prompt.txt. The sandbox is
copied to a temp folder; Claude runs there with its own config dir, so neither your personal setup
nor the dev session leaks in. Each run's cost is appended to eval/ledger.jsonl, and the script refuses
to start once today's spend reaches --daily-cap.

--record keeps the transcript and has the plugin log every hook event; --collect NAME scrubs that
recording into tests/sessions/NAME-<os>/ for replay tests (spike/collect.py).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LEDGER = os.path.join(REPO, "eval", "ledger.jsonl")

TEST_ENV = {
    "CLAUDE_CONFIG_DIR": os.path.expanduser("~/.claude-qlaudified-test"),
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
    "CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT": "1",
    "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",
    "CLAUDE_CODE_DISABLE_BUNDLED_SKILLS": "1",
}


def spent_today():
    if not os.path.exists(LEDGER):
        return 0.0
    today = time.strftime("%Y-%m-%d")
    total = 0.0
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("ts", "").startswith(today):
                total += rec.get("total_cost_usd") or 0.0
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--plugin-dir", default=REPO)
    parser.add_argument("--no-plugin", action="store_true",
                        help="baseline run without any plugin (NFR-1 cost comparison)")
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--daily-cap", type=float, default=2.0, help="USD estimate per day")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help="keep the transcript and record our hook events (QLAUDIFIED_RECORD_DIR)")
    parser.add_argument("--collect", metavar="NAME",
                        help="with --record: scrub the recording into tests/sessions/NAME-<os>/")
    args = parser.parse_args()

    src = os.path.join(REPO, "tests", "sandbox", args.task)
    prompt_file = os.path.join(src, "prompt.txt")
    if not os.path.exists(prompt_file):
        raise SystemExit(f"no task at {src} (needs prompt.txt)")
    with open(prompt_file, encoding="utf-8") as f:
        # Steps separated by "---" lines run in one session, each resuming the last (compaction).
        steps = [s.strip() for s in f.read().split("\n---\n") if s.strip()]

    spent = spent_today()
    if spent >= args.daily_cap:
        raise SystemExit(f"daily cap reached: ${spent:.2f} of ${args.daily_cap:.2f}")

    plugin = [] if args.no_plugin else ["--plugin-dir", os.path.abspath(args.plugin_dir)]
    base = [*plugin,
            "--model", args.model,
            "--max-turns", str(args.max_turns),
            "--allowedTools", "Read,Grep,Glob,Bash,WebFetch,WebSearch",
            "--permission-prompts", "none",
            "--output-format", "json"]
    env = dict(os.environ)
    test_env = dict(TEST_ENV)
    workdir = tempfile.mkdtemp(prefix="qlaudified-")
    sandbox = os.path.join(workdir, args.task)
    record_dir = os.path.join(workdir, "record")
    if args.record or len(steps) > 1:
        # Sprint 0: with this set, -p sessions wrote no transcript under projects/, and --resume
        # needs that transcript.
        del test_env["CLAUDE_CODE_SKIP_PROMPT_HISTORY"]
    if args.record:
        test_env["QLAUDIFIED_RECORD_DIR"] = record_dir
    env.update(test_env)
    if args.dry_run:
        print(json.dumps({"sandbox": src, "steps": steps, "cmd": ["claude", "-p", steps[0], *base],
                          "env": test_env}, indent=2))
        shutil.rmtree(workdir, ignore_errors=True)
        return 0

    shutil.copytree(src, sandbox, ignore=shutil.ignore_patterns("prompt.txt"))

    start = time.time()
    cost, turns, session_id, returncode, stderr = 0.0, 0, None, 0, b""
    for step in steps:
        resume = ["--resume", session_id] if session_id else []
        proc = subprocess.run(["claude", "-p", step, *resume, *base], cwd=sandbox, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, check=False,
                              shell=(os.name == "nt"))
        try:
            data = json.loads(proc.stdout.decode("utf-8", "replace"))
        except ValueError:
            data = {}
        cost += data.get("total_cost_usd") or 0.0
        turns += data.get("num_turns") or 0
        session_id = data.get("session_id") or session_id
        returncode, stderr = proc.returncode, proc.stderr
        if proc.returncode != 0 or not session_id:
            break
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": args.task, "model": args.model,
              "plugin_dir": None if args.no_plugin else args.plugin_dir,
              "returncode": returncode,
              "wall_s": round(time.time() - start, 1),
              "total_cost_usd": round(cost, 6), "num_turns": turns, "steps": len(steps),
              "session_id": session_id, "sandbox": sandbox,
              "result": (data.get("result") or "")[:500]}
    if not os.path.isdir(os.path.dirname(LEDGER)):
        os.makedirs(os.path.dirname(LEDGER))
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    print(json.dumps(record, indent=2))
    if returncode != 0:
        sys.stderr.write(stderr.decode("utf-8", "replace")[-2000:])
    if args.collect and os.path.exists(os.path.join(record_dir, "events.jsonl")):
        subprocess.run([sys.executable, os.path.join(REPO, "spike", "collect.py"), record_dir,
                        args.collect, "--sandbox", sandbox], check=False)
    print(f"sandbox kept for inspection at {sandbox} (delete when done)")
    return returncode


if __name__ == "__main__":
    sys.exit(main())
