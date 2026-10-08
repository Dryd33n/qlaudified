"""Entry point for the ``/qlaudified`` skill: ``launch.sh cli.py <args>``.

Always exits 0: a non-zero exit would abort the skill and hide the message the user needs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    if sys.version_info < (3, 11):
        print("qlaudified needs Python 3.11+, but found %d.%d at %s." % (
            sys.version_info[0], sys.version_info[1], sys.executable))
        sys.exit(0)
    from qlaudified.cli import main

    try:
        main(sys.argv[1:])
    except SystemExit as e:  # argparse usage errors
        if e.code not in (0, None):
            print("Usage: /qlaudified mode [low|medium|high] [--session] | report [--deep] | csv [--path]")
    sys.exit(0)
