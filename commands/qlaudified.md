---
description: qlaudified provenance - mode, report, csv
argument-hint: "mode [low|medium|high] | report [--deep] | csv [--path]"
allowed-tools: ["Bash"]
---

<!-- Skeleton. Sprint 1 wires `mode` (MOD-1..3); Sprint 2 wires `report` and `csv` (REP-2..4).
     The command shells out to qlaudified.cli so the logic stays in Python. -->

Run `python -m qlaudified.cli $ARGUMENTS` from the plugin root (`${CLAUDE_PLUGIN_ROOT}`) and show its output to the user verbatim.
