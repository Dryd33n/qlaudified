"""Write spike/probe/hooks/hooks.json for this machine's Python command. Python 3.7+.

    py -3 spike/make_hooks.py                      # Windows default: "py -3"
    python3 spike/make_hooks.py                    # macOS default: "python3"
    py -3 spike/make_hooks.py --python python      # test the bare `python` command
    py -3 spike/make_hooks.py --no-message-display # if Claude Code rejects the MessageDisplay key
    py -3 spike/make_hooks.py --async-post         # PostToolUse as an async hook (web re-fetch path)
    py -3 spike/make_hooks.py --exec               # exec form: "command" + "args", no shell

Exec form (hooks docs): when "args" is present, "command" is resolved as an executable on PATH and
spawned directly; ${CLAUDE_PLUGIN_ROOT} is substituted into each arg as a plain string, so a space
in the path needs no quoting. On Windows "command" must be a real .exe (py.exe works; check whether
the Store `python` alias does).
"""

import argparse
import json
import os

EVENTS = ["SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact", "Stop",
          "SubagentStop", "SessionEnd", "MessageDisplay"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default="py -3" if os.name == "nt" else "python3")
    parser.add_argument("--no-message-display", action="store_true")
    parser.add_argument("--async-post", action="store_true")
    parser.add_argument("--exec", action="store_true", help="write exec-form hooks (command + args)")
    parser.add_argument("--dual", action="store_true",
                        help="Sprint 1 prep, option (a): one exec hook each for py -3, python3 and a "
                             "missing command, to see how both OSes behave with one hooks.json")
    parser.add_argument("--fallback", action="store_true",
                        help="Sprint 1 prep, option (b): one shell-form hook that runs py -3 if "
                             "it exists, else python3; records $BASH_VERSION to show the shell")
    args = parser.parse_args()

    hooks = {}
    for event in EVENTS:
        if event == "MessageDisplay" and args.no_message_display:
            continue
        if args.fallback:
            probe = '"${CLAUDE_PLUGIN_ROOT}/probe.py" %s' % event
            cmd = ('command -v py >/dev/null 2>&1 && exec py -3 %s via=sh-py "bash=$BASH_VERSION"'
                   ' || exec python3 %s via=sh-python3 "bash=$BASH_VERSION"' % (probe, probe))
            timeout = 150 if event == "Stop" else (10 if event == "MessageDisplay" else 30)
            entry = {"hooks": [{"type": "command", "command": cmd, "timeout": timeout}]}
            if event == "PostToolUse":
                entry["matcher"] = "*"
            hooks[event] = [entry]
            continue
        if args.dual:
            timeout = 150 if event == "Stop" else (10 if event == "MessageDisplay" else 30)
            launchers = [("py", ["-3"]), ("python3", []), ("qlaudified-missing-exe", [])]
            entry = {"hooks": [{"type": "command", "command": exe, "timeout": timeout,
                                "args": pre + ["${CLAUDE_PLUGIN_ROOT}/probe.py", event,
                                               "via=" + exe]}
                               for exe, pre in launchers]}
            if event == "PostToolUse":
                entry["matcher"] = "*"
            hooks[event] = [entry]
            continue
        if args.exec:
            exe, *pre = args.python.split()
            hook = {"type": "command", "command": exe,
                    "args": pre + ["${CLAUDE_PLUGIN_ROOT}/probe.py", event]}
        else:
            # Quoted plugin root: this machine's paths contain spaces ("Dryden Bryson").
            hook = {"type": "command",
                    "command": '%s "${CLAUDE_PLUGIN_ROOT}/probe.py" %s' % (args.python, event)}
        hook["timeout"] = 150 if event == "Stop" else (10 if event == "MessageDisplay" else 30)
        if event == "PostToolUse" and args.async_post:
            hook["async"] = True
        entry = {"hooks": [hook]}
        if event == "PostToolUse":
            entry["matcher"] = "*"
        hooks[event] = [entry]

    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "probe", "hooks", "hooks.json")
    if not os.path.isdir(os.path.dirname(out)):
        os.makedirs(os.path.dirname(out))
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"description": "Sprint 0 probe: log every hook payload", "hooks": hooks}, f,
                  indent=2)
        f.write("\n")
    print("wrote %s (python: %s, form: %s, events: %s)"
          % (out, args.python,
             "fallback" if args.fallback else "dual" if args.dual else
             ("exec" if args.exec else "shell"),
             ", ".join(hooks)))


if __name__ == "__main__":
    main()
