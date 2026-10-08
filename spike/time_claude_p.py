"""Time nested `claude -p --safe-mode` calls per model, to pick the default sidecar model. Python 3.7+.

    py -3 spike/time_claude_p.py --models haiku sonnet --runs 3
    py -3 spike/time_claude_p.py --config-dir ~/.claude-qlaudified-test   # does a separate config dir keep its login?

Uses plan usage (a few tiny calls). Results go to docs/findings/data/claude_p.jsonl.
"""

import argparse
import json
import os
import platform
import subprocess
import time

PROMPT = 'Return JSON {"verdict": "supported"} and nothing else.'


def run_once(model, config_dir):
    env = dict(os.environ)
    if config_dir:
        env["CLAUDE_CONFIG_DIR"] = os.path.expanduser(config_dir)
    cmd = ["claude", "-p", "--safe-mode", "--model", model, "--output-format", "json", PROMPT]
    start = time.perf_counter()
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, timeout=180, shell=(os.name == "nt"))
    wall = round((time.perf_counter() - start) * 1000, 1)
    out = proc.stdout.decode("utf-8", "replace")
    try:
        data = json.loads(out)
    except ValueError:
        data = {}
    return {
        "model": model,
        "config_dir": config_dir,
        "returncode": proc.returncode,
        "wall_ms": wall,
        "duration_ms": data.get("duration_ms"),
        "duration_api_ms": data.get("duration_api_ms"),
        "total_cost_usd": data.get("total_cost_usd"),
        "result": (data.get("result") or out)[:200],
        "stderr": proc.stderr.decode("utf-8", "replace")[:300],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["haiku"])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--config-dir")
    args = parser.parse_args()

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "findings", "data")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(os.path.join(out_dir, "claude_p.jsonl"), "a", encoding="utf-8") as f:
        for model in args.models:
            for _ in range(args.runs):
                r = run_once(model, args.config_dir)
                r.update({"os": platform.platform(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
                f.write(json.dumps(r) + "\n")
                print("%-8s rc=%s wall=%sms api=%sms cost=%s %s" % (
                    model, r["returncode"], r["wall_ms"], r["duration_api_ms"],
                    r["total_cost_usd"], r["result"][:60].replace("\n", " ")))


if __name__ == "__main__":
    main()
