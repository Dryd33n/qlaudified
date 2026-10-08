# qlaudified

Claude Code plugin (Python) that records source spans and verifies claims.
Spec: docs/design.md · Sprints: docs/sprint-plan.md · Testing: docs/testing.md

## Testing
- After any change: `pytest -q -m "not live"` (unit, hook contract, replay). Must pass.
- Hook scripts are tested by piping recorded JSON from tests/sessions and tests/fixtures.
- Live tests: only via `python scripts/live.py <task>`. Ask before running more than one.
- Never run the eval runner unless asked. It uses plan usage.
- Don't open tests/sessions/, tests/fixtures/ or eval/corpus/ unless the task needs it.

## Rules
- Never load this working copy as a plugin in the current session.
- Core code is standard library only; extras go behind [web] / [nli].
- Hooks must never raise: catch, log to .claude/.qlaudified/errors.log, exit 0.
- Hooks are one shell-form line: `py -3 -S` if present, else `python3 -S` (design.md, Hook command).
  Normalize paths: Windows sends backslashes and 8.3 short names.
- Injected context is plain facts, never instructions.
- Tag commits and issues with requirement IDs (CAP-1, VER-4, ...).
- spike/ is throwaway Sprint 0 code; don't import it from the package.
