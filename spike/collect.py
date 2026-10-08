"""Collect a probe recording into tests/sessions/<name>/ and scrub it. Python 3.7+.

    py -3 spike/collect.py <probe_dir> <name> [--sandbox <dir>] [--os windows|macos]

<probe_dir> is a folder the probe wrote (…/.qlaudified-probe/<session_id>/). Copies events.jsonl and
the transcript named in the payloads, optionally snapshots the sandbox, then replaces home paths and
session IDs with placeholders (testing.md, "Recorded sessions as a simulator").
"""

import argparse
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SESSIONS = os.path.join(HERE, "..", "tests", "sessions")


def _win_path(fn, path):
    import ctypes
    buf = ctypes.create_unicode_buffer(32768)
    n = getattr(ctypes.windll.kernel32, fn)(path, buf, len(buf))
    return buf.value if 0 < n < len(buf) else path


def spellings(path):
    """Ways Windows may spell one path. %TEMP% is often 8.3 (C:/Users/DRYDEN~1/AppData/Local/Temp)
    and Claude Code keeps that prefix as-is, so rebuild the path on each env var's own spelling."""
    if os.name != "nt":
        return {path}
    found = {path, _win_path("GetShortPathNameW", path)}
    full = _win_path("GetLongPathNameW", path)
    for var in ("TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA"):
        raw = os.environ.get(var)
        if not raw:
            continue
        long_raw = _win_path("GetLongPathNameW", raw)
        if full.lower().startswith(long_raw.lower()):
            found.add(raw + full[len(long_raw):])
    return found


def mangled(path):
    # Claude Code's projects/<dir> name: every non-alphanumeric character becomes "-".
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def path_variants(path):
    variants = set()
    for p in spellings(path):
        fwd = p.replace("\\", "/")
        variants.update({p, fwd, p.replace("\\", "\\\\"), mangled(p)})
        if len(fwd) > 2 and fwd[1] == ":":  # C:/Users/x -> /c/Users/x (Git Bash form)
            variants.add("/" + fwd[0].lower() + fwd[2:])
    return variants


def placeholders(sandbox):
    pairs = [(v, "<SANDBOX>") for v in path_variants(sandbox)] if sandbox else []
    pairs += [(v, "<HOME>") for v in path_variants(os.path.expanduser("~"))]
    return sorted(pairs, key=lambda kv: len(kv[0]), reverse=True)


def scrub_text(text, session_ids, sandbox=None):
    for v, ph in placeholders(sandbox):
        text = text.replace(v, ph)
    for i, sid in enumerate(sorted(session_ids)):
        text = text.replace(sid, "<SESSION_%d>" % i)
    return EMAIL.sub("<EMAIL>", text)


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Transcript lines the simulator needs. Everything else (system prompt snapshots, skill and tool
# listings, MCP instructions, account/session context) is dropped: it carries account details.
KEEP_TYPES = {"user", "assistant", "system"}


def keep_transcript_line(line):
    try:
        d = json.loads(line)
    except ValueError:
        return False
    if d.get("type") in KEEP_TYPES:
        return True
    return d.get("type") == "attachment" and str((d.get("attachment") or {}).get("type", "")).startswith("hook_")


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

    copies = [(events_path, "events.jsonl", False)]
    for i, t in enumerate(sorted(transcripts)):
        if os.path.exists(t):
            copies.append((t, os.path.join("transcripts", "transcript-%d.jsonl" % i), True))
    for src, rel, is_transcript in copies:
        out = os.path.join(dest, rel)
        if not os.path.isdir(os.path.dirname(out)):
            os.makedirs(os.path.dirname(out))
        with open(src, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if is_transcript:
            text = "".join(line for line in text.splitlines(True) if keep_transcript_line(line))
        with open(out, "w", encoding="utf-8") as f:
            f.write(scrub_text(text, session_ids, args.sandbox and os.path.abspath(args.sandbox)))

    if args.sandbox:
        shutil.copytree(args.sandbox, os.path.join(dest, "sandbox"),
                        ignore=shutil.ignore_patterns(".qlaudified-probe", ".claude"))

    print("collected %d events, %d transcript(s) -> %s" % (len(lines), len(transcripts), dest))
    print("check by eye that no secrets or private paths remain before committing")


if __name__ == "__main__":
    main()
