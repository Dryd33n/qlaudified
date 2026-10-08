"""Backs the ``/qlaudified`` command: ``mode``, ``report [--deep]``, ``csv [--path]``."""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qlaudified")
    sub = parser.add_subparsers(dest="command", required=True)

    mode = sub.add_parser("mode", help="show or set the provenance mode (MOD-1)")
    mode.add_argument("value", nargs="?", choices=["low", "medium", "high"])
    mode.add_argument("--session", action="store_true", help="this session only (MOD-3)")

    report = sub.add_parser("report", help="claim-by-claim report for the last turn (REP-2)")
    report.add_argument("--deep", action="store_true", help="run the LLM tier for this turn")

    csv = sub.add_parser("csv", help="open provenance.csv (REP-3)")
    csv.add_argument("--path", action="store_true", help="print the path instead")

    args = parser.parse_args(argv)
    print(f"qlaudified {args.command}: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
