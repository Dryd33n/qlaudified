"""Write spike/probe/hooks/hooks.json for this machine's Python command. Python 3.7+.

    py -3 spike/make_hooks.py                      # Windows default: "py -3"
    python3 spike/make_hooks.py                    # macOS default: "python3"
    py -3 spike/make_hooks.py --python python      # test the bare `python` command
    py -3 spike/make_hooks.py --no-message-display # if Claude Code rejects the MessageDisplay key
    py -3 spike/make_hooks.py --async-post         # PostToolUse as an async hook (web re-fetch path)
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
    args = parser.parse_args()

    hooks = {}
    for event in EVENTS:
        if event == "MessageDisplay" and args.no_message_display:
            continue
        # Quoted plugin root: this machine's paths contain spaces ("Dryden Bryson").
        hook = {"type": "command",
                "command": '%s "${CLAUDE_PLUGIN_ROOT}/probe.py" %s' % (args.python, event),
                "timeout": 150 if event == "Stop" else 30}
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
    print("wrote %s (python: %s, events: %s)" % (out, args.python, ", ".join(hooks)))


if __name__ == "__main__":
    main()
