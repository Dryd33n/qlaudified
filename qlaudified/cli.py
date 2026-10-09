"""Backs the ``/qlaudified`` command: ``mode``, ``report [--deep]``, ``csv [--path]``, ``nli``.

Run from the project folder. The current session comes from ``CLAUDE_CODE_SESSION_ID``, which
Claude Code sets for the commands it runs.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from qlaudified import config, paths
from qlaudified.store import Store


def _session_id() -> str | None:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or None


def _latest_session_dir(project: Path) -> Path | None:
    """This session's folder if it has a store, else the most recently used one."""
    sessions = paths.store_root({"cwd": str(project)}) / "sessions"
    sid = _session_id()
    if sid and (sessions / paths.safe_name(sid) / "index.sqlite").exists():
        return sessions / paths.safe_name(sid)
    stores = sorted(sessions.glob("*/index.sqlite"), key=lambda p: p.stat().st_mtime)
    return stores[-1].parent if stores else None


def cmd_mode(project: Path, value: str | None, session_only: bool) -> int:
    sid = _session_id()
    if value is None:
        cfg = config.load(project, sid)
        where = {"session": "this session only", "config": "project default",
                 "default": "built-in default"}[cfg.mode_source]
        print(f"qlaudified mode: {cfg.mode} ({where})")
        for problem in cfg.problems:
            print(f"config problem: {problem}")
        return 0
    mode = config.Mode(value)
    if session_only:
        if not sid:
            print("No session ID available; set the project default instead (drop --session).")
            return 1
        config.set_session_mode(project, sid, mode)
        print(f"qlaudified mode: {mode} for this session only; the project default is unchanged.")
    else:
        config.save_mode(project, mode)
        if sid:
            config.set_session_mode(project, sid, None)
        print(f"qlaudified mode: {mode} (saved as the project default in {config.config_path(project)})")
    return 0


def cmd_csv(project: Path, path_only: bool) -> int:
    folder = _latest_session_dir(project)
    if folder is None:
        print("No provenance recorded in this project yet.")
        return 1
    csv_path = Store(folder).export_csv()
    if path_only:
        print(csv_path)
        return 0
    print(f"Opening {csv_path}")
    if sys.platform == "win32":
        os.startfile(csv_path)  # type: ignore[attr-defined]
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, str(csv_path)], check=False)
    return 0


def cmd_report(project: Path, deep: bool = False) -> int:
    """Print the last turn's report (REP-2). A turn recorded in Low mode is verified now;
    ``--deep`` re-verifies it with the LLM tier (one batched call)."""
    folder = _latest_session_dir(project)
    turn = Store(folder).last_turn() if folder is not None else None
    if folder is None or turn is None:
        print("No answers recorded in this project yet.")
        return 1
    md = folder / "reports" / f"turn-{turn.n}.md"
    if deep or not md.exists():
        from qlaudified import report
        from qlaudified.backends import get_backend
        from qlaudified.verify import verify_turn

        cfg = config.load(project, _session_id())
        backend = None
        if deep:
            backend = get_backend(cfg.backend, cfg.backend_model)
            if backend.name == "none":
                print('report --deep needs an LLM backend; config.toml has backend = "none".')
                return 1
        elif cfg.mode == config.Mode.HIGH:
            cfg.mode = config.Mode.MEDIUM  # on request without --deep, check what Medium would
        store = Store(folder)
        result = verify_turn(store, turn, cfg, backend)
        how = f"{cfg.mode}, deep ({backend.name})" if backend else f"{cfg.mode} (on request)"
        md = report.write_turn_report(folder, turn.n, turn.prompt_id, result.claims, result.spans,
                                      result.skipped, how, result.summary_issues)
        store.export_csv()
        if deep and result.usage.get("error"):
            print(f"LLM tier failed ({result.usage['error']}); showing the rule-based verdicts.\n")
    print(md.read_text(encoding="utf-8"), end="")
    return 0


def cmd_nli(action: str) -> int:
    from qlaudified.verify import tier2_nli

    if action == "install":
        try:
            import onnxruntime  # noqa: F401
            import tokenizers  # noqa: F401
        except ImportError:
            print('The NLI tier needs the extra first: pip install "qlaudified[nli]"')
            return 1
        print(f"NLI model installed in {tier2_nli.install()}")
        return 0
    state = "ready" if tier2_nli.available() else "not installed (/qlaudified nli install)"
    print(f"qlaudified NLI tier: {state}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qlaudified")
    sub = parser.add_subparsers(dest="command", required=True)

    mode = sub.add_parser("mode", help="show or set the provenance mode (MOD-1)")
    mode.add_argument("value", nargs="?", choices=["low", "medium", "high"])
    mode.add_argument("--session", action="store_true", help="this session only (MOD-3)")

    report = sub.add_parser("report", help="claim-by-claim report for the last turn (REP-2)")
    report.add_argument("--deep", action="store_true", help="run the LLM tier for this turn")

    nli = sub.add_parser("nli", help="the optional NLI verifier tier (VER-3)")
    nli.add_argument("action", nargs="?", choices=["status", "install"], default="status")

    csv = sub.add_parser("csv", help="open provenance.csv (REP-3)")
    csv.add_argument("--path", action="store_true", help="print the path instead")

    args = parser.parse_args(argv)
    project = paths.project_dir()
    if args.command == "mode":
        return cmd_mode(project, args.value, args.session)
    if args.command == "csv":
        return cmd_csv(project, args.path)
    if args.command == "nli":
        return cmd_nli(args.action)
    return cmd_report(project, args.deep)


if __name__ == "__main__":
    sys.exit(main())
