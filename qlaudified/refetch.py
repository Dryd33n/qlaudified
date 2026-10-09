"""WebFetch shadow re-fetch: the raw page as ``web-raw`` spans, linked to the summary (CAP-3, CAP-4).

WebFetch hands Claude a small model's summary, never the page (Sprint 0), so a qualifier the
summary dropped is invisible without the page itself. PostToolUse calls ``start``, which writes a
pending file and launches ``python -m qlaudified.refetch <pending>`` as a detached process: an
``async`` hook would be killed when a ``claude -p`` session ends (hooks docs), and a detached
process never holds up the agent loop (NFR-4). Stop waits a few seconds for pending fetches.

The summary span's ``derived_from`` then holds the raw span range (``S10-S24``), or
``summarized-only: <reason>`` for paywalls, JS-only pages, timeouts and non-HTML responses.
A page that changed between two fetches gives new spans (spans are unique on their hash).
"""

import contextlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT_S = 10.0
MAX_BYTES = 5_000_000
WAIT_S = 8.0  # Stop waits at most this long for pending fetches
STALE_S = 60.0
USER_AGENT = "Mozilla/5.0 (compatible; qlaudified-refetch/0.1; +local provenance check)"
PAYWALL = re.compile(
    r"subscribe to (?:continue|read)|subscribers only|sign in to (?:continue|read)"
    r"|create a free account to continue|this article is for subscribers", re.IGNORECASE)
JS_ONLY = re.compile(r"enable javascript|javascript is (?:required|disabled)", re.IGNORECASE)

def fetch(url: str, timeout: float = TIMEOUT_S) -> tuple[list[str] | None, str]:
    """(paragraphs, "ok") or (None, reason) for a summarized-only source."""
    if not re.match(r"https?://", url):
        return None, "not an http(s) URL"
    import urllib.error  # here, not at the top: PostToolUse only launches the fetch (NFR-3)
    import urllib.request

    from qlaudified.htmltext import main_text
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "text/html,text/plain;q=0.9"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            kind = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        reason = "paywall or login" if e.code in (401, 402, 403) else f"HTTP {e.code}"
        return None, reason
    except TimeoutError:
        return None, "timeout"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, "timeout" if "timed out" in str(e) else f"fetch failed: {e}"[:120]
    if len(body) > MAX_BYTES:
        return None, "page too large"
    text = body.decode(charset, "replace")
    if kind == "text/plain":
        paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    elif kind in ("text/html", "application/xhtml+xml"):
        paragraphs = main_text(text)
    else:
        return None, f"unsupported content type {kind}"
    joined = " ".join(paragraphs)
    if PAYWALL.search(joined) and len(joined) < 3000:
        return None, "paywall or login"
    if len(joined) < 200:
        return None, "JS-only page" if JS_ONLY.search(text) or "<script" in text else "page has no text"
    return paragraphs, "ok"


# --- running it beside the hook -------------------------------------------------------------

def pending_dir(session_dir: Path) -> Path:
    return Path(session_dir) / "refetch"


def start(session_dir: Path, project: Path, url: str, summary_span_id: str, agent_id: str,
          turn: str | None) -> Path | None:
    """Queue a re-fetch and launch it detached; returns the pending file, or None offline
    (``QLAUDIFIED_OFFLINE=1``: replays and benchmarks never touch the network)."""
    if os.environ.get("QLAUDIFIED_OFFLINE"):
        return None
    folder = pending_dir(session_dir)
    folder.mkdir(parents=True, exist_ok=True)
    pending = folder / f"{summary_span_id}.json"
    pending.write_text(json.dumps({
        "url": url, "summary_span_id": summary_span_id, "agent_id": agent_id, "turn": turn,
        "session_dir": str(session_dir), "project": str(project), "started": time.time(),
    }), encoding="utf-8")
    root = Path(__file__).resolve().parent.parent
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL, "cwd": str(root), "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, "-S", "-m", "qlaudified.refetch", str(pending)], **kwargs)
    return pending


def run(pending: Path) -> str:
    """Fetch one queued page, store its spans and link the summary. Returns the outcome."""
    from qlaudified import capture, config
    from qlaudified.store import Store

    job = json.loads(Path(pending).read_text(encoding="utf-8"))
    store = Store(job["session_dir"])
    try:
        paragraphs, reason = fetch(job["url"])
        if paragraphs is None:
            store.set_derived_from(job["summary_span_id"], f"summarized-only: {reason}")
            return reason
        lex = config.load(job["project"]).lexicon()
        spans = [capture.indexed("web-raw", job["url"], f"p{i}", text, job["agent_id"],
                                 job["turn"], lex) for i, text in enumerate(paragraphs, 1)]
        ids = store.add_spans(spans)
        nums = sorted(int(i[1:]) for i in ids)
        store.set_derived_from(job["summary_span_id"], f"S{nums[0]}-S{nums[-1]}")
        return "ok"
    finally:
        Path(pending).unlink(missing_ok=True)


def wait_for_pending(session_dir: Path, max_s: float = WAIT_S) -> None:
    """Let in-flight fetches finish before Stop verifies; stale ones are skipped."""
    folder = pending_dir(session_dir)
    deadline = time.time() + max_s
    while folder.is_dir():
        live = [p for p in folder.glob("*.json") if time.time() - p.stat().st_mtime < STALE_S]
        if not live or time.time() > deadline:
            return
        time.sleep(0.1)


def main(argv: list[str]) -> int:
    pending = Path(argv[0])
    try:
        run(pending)
    except Exception:  # noqa: BLE001 - detached: log, never raise
        with contextlib.suppress(Exception):
            from qlaudified.log import log_error

            job = json.loads(pending.read_text(encoding="utf-8")) if pending.exists() else {}
            log_error("Refetch", {"cwd": job.get("project")}, 0.0)
            pending.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("QLAUDIFIED_NESTED", "1")
    sys.exit(main(sys.argv[1:]))
