---
description: Record a new session for the simulator
argument-hint: "<scenario>"
---

Follow the "Recording sessions" steps in spike/README.md for scenario `$ARGUMENTS`: run it with the probe plugin, then collect and scrub it into tests/sessions/$ARGUMENTS/ with `py -3 spike/collect.py`. Do not open the recorded files beyond checking they exist.
