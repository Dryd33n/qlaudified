"""WebFetch shadow re-fetch: raw page + main text, linked to the summary span (CAP-3, CAP-4).

Runs as an async hook. Falls back to ``summarized-only`` on paywalls, JS-only pages, timeouts and
hash mismatches. Sprint 3.
"""


def refetch(url: str, timeout_s: float = 10.0) -> str | None:
    raise NotImplementedError("Sprint 3: CAP-3")
