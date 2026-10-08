#!/bin/sh
# Run a qlaudified script with the right Python: py -3 where the launcher exists (Windows),
# else python3 (docs/design.md, Hook command). Usage: sh launch.sh <script.py> [args...]
here=$(dirname "$0")
script="$1"
shift
if command -v py >/dev/null 2>&1; then
    exec py -3 "$here/$script" "$@"
fi
exec python3 "$here/$script" "$@"
