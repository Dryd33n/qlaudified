"""``qlaudified-sim tests/sessions/<name>``: replay a recorded session through the real hook entry point.

Rebuilds the sandbox in a temp folder, swaps the scrub placeholders (``<SANDBOX>``, ``<HOME>``,
``<SESSION_n>``) for real values, then pipes each event in events.jsonl to ``hooks/run.py <event>``
with the env Claude Code would set. Recordings come from spike/collect.py.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_PY = REPO / "hooks" / "run.py"


def substitute(obj, mapping: dict[str, str]):
    """Replace placeholders inside every string of a parsed JSON value."""
    if isinstance(obj, str):
        for key, value in mapping.items():
            obj = obj.replace(key, value)
        return re.sub(r"<SESSION_(\d+)>", r"sim-session-\1", obj)
    if isinstance(obj, list):
        return [substitute(v, mapping) for v in obj]
    if isinstance(obj, dict):
        return {k: substitute(v, mapping) for k, v in obj.items()}
    return obj


def placeholders(workdir: Path) -> dict[str, str]:
    return {"<SANDBOX>": str(workdir / "sandbox"), "<HOME>": str(workdir / "home")}


@dataclass
class Replay:
    project: Path
    calls: list[tuple[str, int, str]] = field(default_factory=list)  # event, returncode, stdout


def replay(session: Path, workdir: Path) -> Replay:
    """Pipe every recorded event through hooks/run.py; the project is the first payload's cwd."""
    mapping = placeholders(workdir)
    sandbox = workdir / "sandbox"
    if (session / "sandbox").is_dir():
        shutil.copytree(session / "sandbox", sandbox, dirs_exist_ok=True)
    sandbox.mkdir(parents=True, exist_ok=True)

    records = [json.loads(line) for line in
               (session / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    first: dict = next((r["payload"] for r in records if isinstance(r.get("payload"), dict)), {})
    project = Path(substitute(first.get("cwd") or "<SANDBOX>", mapping))
    project.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project), "CLAUDE_PLUGIN_ROOT": str(REPO),
           "QLAUDIFIED_OFFLINE": "1"}  # a replayed WebFetch must not re-fetch the live page

    result = Replay(project=project)
    for rec in records:
        payload = substitute(rec.get("payload"), mapping)
        data = json.dumps(payload) if payload is not None else (rec.get("raw") or "")
        proc = subprocess.run(
            [sys.executable, str(RUN_PY), rec["event"]], input=data.encode("utf-8"),
            capture_output=True, env=env, timeout=60, check=False,
        )
        result.calls.append((rec["event"], proc.returncode, proc.stdout.decode("utf-8", "replace")))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qlaudified-sim")
    parser.add_argument("session", help="path to tests/sessions/<name>")
    parser.add_argument("--keep", action="store_true", help="keep the temp folder for inspection")
    args = parser.parse_args(argv)

    workdir = Path(tempfile.mkdtemp(prefix="qlaudified-sim-"))
    try:
        result = replay(Path(args.session), workdir)
        failed = [c for c in result.calls if c[1] != 0]
        for event, code, out in result.calls:
            print(f"{event:18} rc={code} {out[:100]}")
        print(f"{len(result.calls)} events, {len(failed)} failed; project: {result.project}")
        return 1 if failed else 0
    finally:
        if args.keep:
            print(f"kept {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
