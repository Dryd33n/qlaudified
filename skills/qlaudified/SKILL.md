---
name: qlaudified
description: qlaudified provenance tracking - show or set the mode (low, medium, high), open provenance.csv, or show the claim report.
argument-hint: "mode [low|medium|high] [--session] | report [--deep] | csv [--path] | nli [install]"
disable-model-invocation: true
allowed-tools: Bash(sh *launch.sh cli.py*)
---

!`sh "${CLAUDE_PLUGIN_ROOT}/hooks/launch.sh" cli.py $ARGUMENTS`

Show the qlaudified output above to the user exactly as written, and take no other action.
