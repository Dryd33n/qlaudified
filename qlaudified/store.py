"""Session store: SQLite (WAL, busy timeout) is the source of truth; provenance.csv is an export.

Layout per session: index.sqlite, provenance.csv, raw/<hash>.txt, reports/turn-<n>.{md,json},
usage.jsonl. Several hook processes write at once (parallel tool calls), so every write is one
short ``BEGIN IMMEDIATE`` transaction. The store root gets a ``.gitignore`` on first use.
"""

import csv
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from qlaudified.paths import ensure_gitignore

TEXT_CAP = 4000  # chars kept in the index; longer text goes to raw/<hash>.txt


@dataclass
class Span:
    span_id: str  # "S14"
    origin: str  # local-doc | code | command-output | web-raw | web-summary | search-snippet | mcp | user-prompt
    source: str  # project-relative path, URL, or "mcp:<server>/<tool>"
    locator: str  # "L22-L24" or "p7"
    text: str
    numbers: str = ""
    qualifiers: str = ""
    derived_from: str | None = None
    agent_id: str = "main"
    turn: str | None = None  # prompt_id
    ts: str = ""
    hash: str = ""


@dataclass
class Claim:
    claim_id: str
    turn: str
    text: str
    span_ids: list[str]
    # supported | partial | qualifier-dropped | contradicted | unsupported | inference | unresolved
    verdict: str
    dropped_qualifiers: list[str]
    decided_by: str  # deterministic | nli | llm
    confidence: float
    critical: bool


SPAN_FIELDS = [f.name for f in fields(Span)]

SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    span_id TEXT UNIQUE, origin TEXT, source TEXT, locator TEXT, text TEXT, numbers TEXT,
    qualifiers TEXT, derived_from TEXT, agent_id TEXT, turn TEXT, ts TEXT, hash TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS spans_same_passage ON spans(source, locator, hash, agent_id);
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY, turn TEXT, text TEXT, span_ids TEXT, verdict TEXT,
    dropped_qualifiers TEXT, decided_by TEXT, confidence REAL, critical INTEGER
);
"""


class Store:
    def __init__(self, session_dir) -> None:
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        ensure_gitignore(self.session_dir.parent.parent)
        self.db_path = self.session_dir / "index.sqlite"
        self.csv_path = self.session_dir / "provenance.csv"

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        con.execute("PRAGMA busy_timeout = 10000")
        # Switching to WAL and creating the schema ignore the busy timeout, and parallel hooks
        # race to do both on a new database, so retry them; skip them once done.
        for attempt in range(200):
            try:
                if con.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                    con.execute("PRAGMA journal_mode = WAL")
                if not con.execute("SELECT 1 FROM sqlite_master WHERE name = 'claims'").fetchone():
                    con.executescript(SCHEMA)
                return con
            except sqlite3.OperationalError as e:
                if "locked" not in str(e) and "busy" not in str(e) or attempt == 199:
                    con.close()
                    raise
                time.sleep(0.01 + 0.0002 * attempt)
        return con

    def add_span(self, span: Span) -> str:
        return self.add_spans([span])[0]

    def add_spans(self, spans: list[Span]) -> list[str]:
        """Store spans and return their IDs. A passage the same agent saw before keeps its first ID;
        a subagent reading it gets its own span, since its context is separate (CAP-6)."""
        ids = []
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            for span in spans:
                row = asdict(span)
                row["ts"] = row["ts"] or time.strftime("%Y-%m-%dT%H:%M:%S%z")
                if len(row["text"]) > TEXT_CAP:
                    self._save_raw(row["hash"], row["text"])
                    row["text"] = row["text"][:TEXT_CAP]
                cols = [c for c in SPAN_FIELDS if c != "span_id"]
                cur = con.execute(
                    f"INSERT OR IGNORE INTO spans ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' for _ in cols)})",
                    [row[c] for c in cols],
                )
                if cur.rowcount == 1:
                    span_id = f"S{cur.lastrowid}"
                    con.execute("UPDATE spans SET span_id = ? WHERE seq = ?", (span_id, cur.lastrowid))
                else:
                    span_id = con.execute(
                        "SELECT span_id FROM spans "
                        "WHERE source = ? AND locator = ? AND hash = ? AND agent_id = ?",
                        (row["source"], row["locator"], row["hash"], row["agent_id"]),
                    ).fetchone()[0]
                span.span_id = span_id
                ids.append(span_id)
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        return ids

    def _save_raw(self, digest: str, text: str) -> None:
        raw = self.session_dir / "raw"
        raw.mkdir(exist_ok=True)
        (raw / f"{digest or 'nohash'}.txt").write_text(text, encoding="utf-8")

    def spans(self) -> list[Span]:
        con = self._connect()
        try:
            rows = con.execute(f"SELECT {', '.join(SPAN_FIELDS)} FROM spans ORDER BY seq").fetchall()
        finally:
            con.close()
        return [Span(**dict(zip(SPAN_FIELDS, r, strict=True))) for r in rows]

    def spans_since(self, marker: str | None) -> list[Span]:
        raise NotImplementedError("Sprint 2: INJ-1")

    def add_claims(self, claims: list[Claim]) -> None:
        raise NotImplementedError("Sprint 2: VER-2")

    def export_csv(self) -> Path:
        """Write provenance.csv atomically. Raises if the file is locked (open in Excel)."""
        tmp = self.csv_path.with_suffix(f".{os.getpid()}.tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(SPAN_FIELDS)
            for span in self.spans():
                writer.writerow([getattr(span, c) or "" for c in SPAN_FIELDS])
        os.replace(tmp, self.csv_path)
        return self.csv_path
