"""Post-compaction digest of critical spans and qualifiers, via SessionStart ``compact`` (INJ-3).

Compaction summaries keep the gist and drop qualifiers, so the main agent gets its qualified and
numeric spans back in the injection line format, strongest hedges first, within the budget.
"""

from qlaudified import inject
from qlaudified.store import Store

HEADER = "Provenance recorded earlier in this session (qlaudified):"


def build_digest(store: Store, budget_chars: int, csv_path: str = "") -> str:
    spans = [s for s in store.spans() if s.agent_id == "main"]
    header = f"{HEADER} (full ledger: {csv_path})" if csv_path else HEADER
    return inject.build_delta(spans, budget_chars, header=header, csv_path=csv_path)
