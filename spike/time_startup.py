"""Time Python startup for each candidate hook command (NFR-3 headroom). Python 3.7+.

    py -3 spike/time_startup.py [--runs 20]

Each run starts the interpreter and imports what a capture hook needs (json, sqlite3, re, hashlib).
Results are appended to docs/findings/data/startup.jsonl.
"""

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
import time

SNIPPET = "import json, sqlite3, re, hashlib, sys; sys.stdout.write(sys.version.split()[0])"


def candidates():
    if os.name == "nt":
        return ["python", "py -3", "python3", '"%s"' % sys.executable]
    return ["python3", "python", '"%s"' % sys.executable]


def time_cmd(cmd, runs):
    argv = shlex.split(cmd, posix=(os.name != "nt")) + ["-c", SNIPPET]
    argv = [a.strip('"') for a in argv]
    times, version, error = [], None, None
    for _ in range(runs):
        start = time.perf_counter()
        try:
            proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        except Exception as e:  # noqa: BLE001
            error = repr(e)
            break
        times.append((time.perf_counter() - start) * 1000)
        if proc.returncode != 0:
            error = proc.stderr.decode("utf-8", "replace").strip()[:300] or "exit %d" % proc.returncode
            break
        version = proc.stdout.decode().strip()
    times.sort()
    pct = lambda p: round(times[min(len(times) - 1, int(p * len(times)))], 1) if times else None  # noqa: E731
    return {"cmd": cmd, "version": version, "error": error, "runs": len(times),
            "p50_ms": pct(0.5), "p95_ms": pct(0.95)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "findings", "data")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(os.path.join(out_dir, "startup.jsonl"), "a", encoding="utf-8") as f:
        for cmd in candidates():
            r = time_cmd(cmd, args.runs)
            r.update({"os": platform.platform(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
            f.write(json.dumps(r) + "\n")
            print("%-45s version=%-8s p50=%-7s p95=%-7s %s" % (
                cmd, r["version"], r["p50_ms"], r["p95_ms"], r["error"] or ""))


if __name__ == "__main__":
    main()
