"""Run one live task in an isolated `claude -p` session with a plugin under test (testing.md).

    python scripts/live.py <task> [--plugin-dir DIR] [--model haiku] [--max-turns 6] [--dry-run]

<task> names tests/sandbox/<task>/, which holds the sandbox files and a prompt.txt. The sandbox is
copied to a temp folder; Claude runs there with its own config dir, so neither your personal setup
nor the dev session leaks in. Each run's cost is appended to eval/ledger.jsonl, and the script refuses
to start once today's spend reaches --daily-cap.

Sprint 0 uses --plugin-dir spike/probe to record sessions. Assertions on the store arrive in Sprint 1.
Kept Python 3.7 compatible until the dev machine has 3.10+.
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
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--daily-cap", type=float, default=2.0, help="USD estimate per day")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help="keep the session transcript (for tests/sessions recordings)")
    args = parser.parse_args()

    src = os.path.join(REPO, "tests", "sandbox", args.task)
    prompt_file = os.path.join(src, "prompt.txt")
    if not os.path.exists(prompt_file):
        raise SystemExit("no task at %s (needs prompt.txt)" % src)
    with open(prompt_file, encoding="utf-8") as f:
        prompt = f.read().strip()

    spent = spent_today()
    if spent >= args.daily_cap:
        raise SystemExit("daily cap reached: $%.2f of $%.2f" % (spent, args.daily_cap))


    cmd = ["claude", "-p", prompt,
           "--plugin-dir", os.path.abspath(args.plugin_dir),
           "--model", args.model,
           "--max-turns", str(args.max_turns),
           "--allowedTools", "Read,Grep,Glob,Bash,WebFetch,WebSearch",
           "--permission-prompts", "none",
           "--output-format", "json"]
    env = dict(os.environ)
    test_env = dict(TEST_ENV)
    if args.record:
        # Sprint 0: with this set, -p sessions wrote no transcript under projects/.
        del test_env["CLAUDE_CODE_SKIP_PROMPT_HISTORY"]
    env.update(test_env)
    if args.dry_run:
        print(json.dumps({"sandbox": src, "cmd": cmd, "env": test_env}, indent=2))
        return 0

    sandbox = os.path.join(tempfile.mkdtemp(prefix="qlaudified-"), args.task)
    shutil.copytree(src, sandbox, ignore=shutil.ignore_patterns("prompt.txt"))

    start = time.time()
    proc = subprocess.run(cmd, cwd=sandbox, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=(os.name == "nt"))
    out = proc.stdout.decode("utf-8", "replace")
    try:
        data = json.loads(out)
    except ValueError:
        data = {}
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": args.task, "model": args.model,
              "plugin_dir": args.plugin_dir, "returncode": proc.returncode,
              "wall_s": round(time.time() - start, 1),
              "total_cost_usd": data.get("total_cost_usd"), "num_turns": data.get("num_turns"),
              "session_id": data.get("session_id"), "sandbox": sandbox}
    if not os.path.isdir(os.path.dirname(LEDGER)):
        os.makedirs(os.path.dirname(LEDGER))
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    print(json.dumps(record, indent=2))
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:])
    print("sandbox kept for inspection at %s (delete when done)" % sandbox)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
