"""WebFetch shadow re-fetch: the raw page as ``web-raw`` spans, linked to the summary (CAP-3, CAP-4).

WebFetch hands Claude a small model's summary, never the page (Sprint 0), so a qualifier the
summary dropped is invisible without the page itself. PostToolUse calls ``start``, which writes a
job for ``python -m qlaudified.refetch`` as a detached process (background.py); Stop waits a few
seconds for it.

The summary span's ``derived_from`` then holds the raw span range (``S10-S24``), or
``summarized-only: <reason>`` for paywalls, JS-only pages, timeouts and non-HTML responses.
A page that changed between two fetches gives new spans (spans are unique on their hash).
"""

import re
import sys
from pathlib import Path

TIMEOUT_S = 10.0
MAX_BYTES = 5_000_000
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

def start(session_dir: Path, project: Path, url: str, summary_span_id: str, agent_id: str,
          turn: str | None) -> Path | None:
    """Queue a re-fetch and launch it detached (background.py); None when offline."""
    from qlaudified import background

    return background.launch(session_dir, "qlaudified.refetch", f"refetch-{summary_span_id}", {
        "url": url, "summary_span_id": summary_span_id, "agent_id": agent_id, "turn": turn,
        "project": str(project)})


def run(job: dict) -> str:
    """Fetch one queued page, store its spans and link the summary. Returns the outcome."""
    from qlaudified import capture, config
    from qlaudified.store import Store

    store = Store(job["session_dir"])
    paragraphs, reason = fetch(job["url"])
    if paragraphs is None:
        store.set_derived_from(job["summary_span_id"], f"summarized-only: {reason}")
        return reason
    lex = config.load(job["project"]).lexicon()
    facts = [f for i, text in enumerate(paragraphs, 1)
             for f in capture.facts_from_passage("web-raw", job["url"], f"p{i}", text,
                                                 job["agent_id"], job["turn"], lex,
                                                 "Direct Retrieved Fact")]
    if not facts:
        store.set_derived_from(job["summary_span_id"], "page has no facts")
        return "ok"
    nums = sorted(int(i[1:]) for i in store.add_spans(facts))
    store.set_derived_from(job["summary_span_id"], f"F{nums[0]}-F{nums[-1]}")
    store.export_csv()
    return "ok"


if __name__ == "__main__":
    from qlaudified.background import run_job

    sys.exit(run_job(sys.argv[1:], run, "Refetch"))
