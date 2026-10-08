"""Collect a probe recording into tests/sessions/<name>/ and scrub it. Python 3.7+.

    py -3 spike/collect.py <probe_dir> <name> [--sandbox <dir>] [--os windows|macos]

<probe_dir> is a folder the probe wrote (…/.qlaudified-probe/<session_id>/). Copies events.jsonl and
the transcript named in the payloads, optionally snapshots the sandbox, then replaces home paths and
session IDs with placeholders (testing.md, "Recorded sessions as a simulator").
"""

import argparse
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SESSIONS = os.path.join(HERE, "..", "tests", "sessions")


def home_variants():
    home = os.path.expanduser("~")
    fwd = home.replace("\\", "/")
    variants = {home, fwd, home.replace("\\", "\\\\")}
    if len(fwd) > 2 and fwd[1] == ":":  # C:/Users/x -> /c/Users/x (Git Bash form)
        variants.add("/" + fwd[0].lower() + fwd[2:])
    return sorted(variants, key=len, reverse=True)


def scrub_text(text, session_ids):
    for v in home_variants():
        text = text.replace(v, "<HOME>")
    for i, sid in enumerate(sorted(session_ids)):
        text = text.replace(sid, "<SESSION_%d>" % i)
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("probe_dir")
    parser.add_argument("name")
    parser.add_argument("--sandbox", help="folder the session ran in, snapshotted to sandbox/")
    parser.add_argument("--os", default="windows" if os.name == "nt" else "macos")
    args = parser.parse_args()

    dest = os.path.abspath(os.path.join(SESSIONS, "%s-%s" % (args.name, args.os)))
    if os.path.exists(dest):
        raise SystemExit("refusing to overwrite %s" % dest)
    os.makedirs(dest)

    events_path = os.path.join(args.probe_dir, "events.jsonl")
    with open(events_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    session_ids, transcripts = set(), set()
    for rec in lines:
        p = rec.get("payload") or {}
        if p.get("session_id"):
            session_ids.add(p["session_id"])
        if p.get("transcript_path"):
            transcripts.add(p["transcript_path"])

    copies = [(events_path, "events.jsonl")]
    for t in sorted(transcripts):
        if os.path.exists(t):
            copies.append((t, os.path.join("transcripts", os.path.basename(t))))
    for src, rel in copies:
        out = os.path.join(dest, rel)
        if not os.path.isdir(os.path.dirname(out)):
            os.makedirs(os.path.dirname(out))
        with open(src, encoding="utf-8", errors="replace") as f:
            text = f.read()
        with open(out, "w", encoding="utf-8") as f:
            f.write(scrub_text(text, session_ids))

    if args.sandbox:
        shutil.copytree(args.sandbox, os.path.join(dest, "sandbox"),
                        ignore=shutil.ignore_patterns(".qlaudified-probe", ".claude"))

    print("collected %d events, %d transcript(s) -> %s" % (len(lines), len(transcripts), dest))
    print("check by eye that no secrets or private paths remain before committing")


if __name__ == "__main__":
    main()
