"""``qlaudified-sim tests/sessions/<name>``: replay a recorded session through the real hook entry point.

Rebuilds the sandbox in a temp folder, then pipes each event in events.jsonl to
``hooks/run.py <event>`` with the env Claude Code would set. Sprint 1-2.
"""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qlaudified-sim")
    parser.add_argument("session", help="path to tests/sessions/<name>")
    parser.parse_args(argv)
    print("qlaudified-sim: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
