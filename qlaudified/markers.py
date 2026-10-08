"""Inline answer markers such as ``[S3]``, ``[S3, qualifier: estimated]``, ``[unsupported]`` (REP-1).

Approach depends on the Sprint 0 MessageDisplay findings: markers come from fast deterministic span
matching at display time; full verdicts arrive at Stop. Sprint 2.
"""


def add_markers(text: str, store) -> str:
    raise NotImplementedError("Sprint 2: REP-1")
