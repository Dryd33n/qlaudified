"""WebFetch shadow re-fetch against saved pages on a local server (CAP-3, CAP-4)."""

from pathlib import Path

import pytest

from qlaudified import htmltext, refetch
from qlaudified.config import Config
from qlaudified.store import Span, Store
from qlaudified.testing.webserver import serve
from qlaudified.verify import evidence, summary_issues

WEB = Path(__file__).resolve().parents[1] / "fixtures" / "web"


@pytest.fixture(scope="module")
def site():
    server, url = serve(WEB)
    yield url
    server.shutdown()


def test_main_text_keeps_the_article_and_drops_navigation():
    paragraphs = htmltext.main_text((WEB / "pricing.html").read_text(encoding="utf-8"))
    assert paragraphs[0] == "Fernwick Ledger pricing" or "Pricing is expected" in paragraphs[0]
    assert ("Pricing is expected to start at $12 per seat per month, subject to change after the "
            "beta.") in paragraphs
    assert not any("Privacy policy" in p or "Blog" in p or "analytics" in p for p in paragraphs)


def test_fetch_outcomes(site):
    paragraphs, status = refetch.fetch(f"{site}/pricing.html")
    assert status == "ok" and len(paragraphs) >= 3
    assert refetch.fetch(f"{site}/app.html") == (None, "JS-only page")
    assert refetch.fetch(f"{site}/paywall") == (None, "paywall or login")
    assert refetch.fetch(f"{site}/missing.html") == (None, "HTTP 404")
    assert refetch.fetch(f"{site}/slow/pricing.html", timeout=0.3) == (None, "timeout")
    assert refetch.fetch("file:///etc/passwd") == (None, "not an http(s) URL")


def summary_span(url: str, text: str) -> Span:
    return Span("", "web-summary", url, "summary", text, "12 USD", "", hash="sum")


def job(tmp_path, store: Store, url: str) -> dict:
    [span_id] = store.add_spans([summary_span(url, "Pricing starts at $12 per seat per month.")])
    return {"url": url, "summary_span_id": span_id, "agent_id": "main", "turn": "p1",
            "session_dir": str(store.session_dir), "project": str(tmp_path)}


def test_run_stores_the_page_and_links_the_summary(site, tmp_path):
    store = Store(tmp_path / "s")
    assert refetch.run(job(tmp_path, store, f"{site}/pricing.html")) == "ok"
    spans = store.spans()
    summary, raw = spans[0], spans[1:]
    assert {s.origin for s in raw} == {"web-raw"} and raw[0].locator == "p1"
    assert summary.derived_from == f"{raw[0].span_id}-{raw[-1].span_id}"
    priced = next(s for s in raw if "$12" in s.text)
    assert priced.qualifiers == "expected to; subject to change" and "12 USD" in priced.numbers


def test_a_failed_fetch_marks_the_summary_summarized_only(site, tmp_path):
    store = Store(tmp_path / "s")
    assert refetch.run(job(tmp_path, store, f"{site}/paywall")) == "paywall or login"
    assert store.spans()[0].derived_from == "summarized-only: paywall or login"


def test_qualifiers_webfetch_dropped_are_flagged_and_the_page_is_the_evidence(site, tmp_path):
    store = Store(tmp_path / "s")
    refetch.run(job(tmp_path, store, f"{site}/pricing.html"))
    spans = store.spans()
    assert all(s.origin == "web-raw" for s in evidence(spans))  # the summary gives way to the page
    [issue] = summary_issues(spans, Config())
    assert issue["verdict"] == "qualifier-dropped"
    assert issue["dropped_qualifiers"] == ["subject to change", "expected to"]
    assert issue["text"] == "Pricing starts at $12 per seat per month."


def test_wait_for_pending_returns_once_jobs_finish(tmp_path):
    import threading

    from qlaudified import background

    folder = background.pending_dir(tmp_path)
    folder.mkdir()
    (folder / "refetch-S1.json").write_text("{}")
    threading.Timer(0.3, (folder / "refetch-S1.json").unlink).start()
    background.wait_for_pending(tmp_path, max_s=5)
    assert not (folder / "refetch-S1.json").exists()
