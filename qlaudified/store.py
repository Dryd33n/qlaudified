"""Session store: SQLite (WAL, busy timeout) is the source of truth; provenance.csv is an export.

Layout per session: index.sqlite, provenance.csv, raw/<hash>.txt, reports/turn-<n>.{md,json},
usage.jsonl. Several hook processes write at once (parallel tool calls), so every write is one
short ``BEGIN IMMEDIATE`` transaction. The store root gets a ``.gitignore`` on first use. Turns are
numbered in the order their Stop arrives and keyed by ``prompt_id``.
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
    claim_id: str  # "C2.1": turn 2, first claim
    turn: str  # prompt_id
    text: str
    span_ids: list[str]
    # supported | partial | qualifier-dropped | contradicted | unsupported | inference | unresolved
    verdict: str
    dropped_qualifiers: list[str]
    decided_by: str  # deterministic | nli | llm | none
    confidence: float
    critical: bool


@dataclass
class Turn:
    n: int
    prompt_id: str
    answer: str
    ts: str


SPAN_FIELDS = [f.name for f in fields(Span)]
CLAIM_FIELDS = [f.name for f in fields(Claim)]
# provenance.csv: one row per span, then one per claim; claim rows reuse turn and text.
CSV_FIELDS = ["kind", *SPAN_FIELDS, "claim_id", "verdict", "span_ids", "dropped_qualifiers",
              "decided_by", "confidence", "critical"]

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
CREATE TABLE IF NOT EXISTS turns (
    n INTEGER PRIMARY KEY AUTOINCREMENT, prompt_id TEXT UNIQUE, answer TEXT, ts TEXT
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
                if not con.execute("SELECT 1 FROM sqlite_master WHERE name = 'turns'").fetchone():
                    con.executescript(SCHEMA)
                return con
            except sqlite3.OperationalError as e:
                if "locked" not in str(e) and "busy" not in str(e) or attempt == 199:
                    con.close()
                    raise
                time.sleep(0.01 + 0.0002 * attempt)
        return con

    def _query(self, sql: str, args: tuple = ()) -> list[tuple]:
        con = self._connect()
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def add_span(self, span: Span) -> str:
        return self.add_spans([span])[0]

    def add_spans(self, spans: list[Span]) -> list[str]:
        """Store spans and return their IDs. A passage the same agent saw before keeps its first ID;
        a subagent reading it gets its own span, since its context is separate (CAP-6)."""
        return [span_id for span_id, _ in self._insert(spans)]

    def add_new_spans(self, spans: list[Span]) -> list[Span]:
        """Store spans and return only those this agent hadn't seen: the delta to inject (INJ-1).

        Each hook call injects its own new rows, so parallel tool calls never inject a row twice."""
        return [span for span, (_, new) in zip(spans, self._insert(spans), strict=True) if new]

    def _insert(self, spans: list[Span]) -> list[tuple[str, bool]]:
        out = []
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
                new = cur.rowcount == 1
                if new:
                    span_id = f"S{cur.lastrowid}"
                    con.execute("UPDATE spans SET span_id = ? WHERE seq = ?", (span_id, cur.lastrowid))
                else:
                    span_id = con.execute(
                        "SELECT span_id FROM spans "
                        "WHERE source = ? AND locator = ? AND hash = ? AND agent_id = ?",
                        (row["source"], row["locator"], row["hash"], row["agent_id"]),
                    ).fetchone()[0]
                span.span_id = span_id
                out.append((span_id, new))
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        return out

    def _save_raw(self, digest: str, text: str) -> None:
        raw = self.session_dir / "raw"
        raw.mkdir(exist_ok=True)
        (raw / f"{digest or 'nohash'}.txt").write_text(text, encoding="utf-8")

    def spans(self, with_numbers: bool = False) -> list[Span]:
        where = " WHERE numbers != ''" if with_numbers else ""
        rows = self._query(f"SELECT {', '.join(SPAN_FIELDS)} FROM spans{where} ORDER BY seq")
        return [Span(**dict(zip(SPAN_FIELDS, r, strict=True))) for r in rows]

    def start_turn(self, prompt_id: str, answer: str) -> Turn:
        """Record a turn's final answer; a second Stop in the same turn updates it and keeps its n."""
        ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO turns (prompt_id, answer, ts) VALUES (?, ?, ?) ON CONFLICT(prompt_id) "
                "DO UPDATE SET answer = excluded.answer, ts = excluded.ts",
                (prompt_id, answer, ts),
            )
            n = con.execute("SELECT n FROM turns WHERE prompt_id = ?", (prompt_id,)).fetchone()[0]
        finally:
            con.close()
        return Turn(n, prompt_id, answer, ts)

    def last_turn(self) -> Turn | None:
        rows = self._query("SELECT n, prompt_id, answer, ts FROM turns ORDER BY n DESC LIMIT 1")
        return Turn(*rows[0]) if rows else None

    def add_claims(self, turn: str, claims: list[Claim]) -> None:
        """Replace the turn's claims, so a re-verified turn keeps no stale verdicts."""
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM claims WHERE turn = ?", (turn,))
            con.executemany(
                f"INSERT INTO claims ({', '.join(CLAIM_FIELDS)}) "
                f"VALUES ({', '.join('?' for _ in CLAIM_FIELDS)})",
                [(c.claim_id, c.turn, c.text, "; ".join(c.span_ids), c.verdict,
                  "; ".join(c.dropped_qualifiers), c.decided_by, c.confidence, int(c.critical))
                 for c in claims],
            )
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def claims(self, turn: str | None = None) -> list[Claim]:
        where, args = (" WHERE c.turn = ?", (turn,)) if turn is not None else ("", ())
        rows = self._query(
            f"SELECT {', '.join('c.' + f for f in CLAIM_FIELDS)} FROM claims c "
            f"LEFT JOIN turns t ON t.prompt_id = c.turn{where} ORDER BY t.n, c.rowid",
            args,
        )
        out = []
        for r in rows:
            c = Claim(**dict(zip(CLAIM_FIELDS, r, strict=True)))
            c.span_ids = [s for s in str(c.span_ids or "").split("; ") if s]
            c.dropped_qualifiers = [s for s in str(c.dropped_qualifiers or "").split("; ") if s]
            c.critical = bool(c.critical)
            out.append(c)
        return out

    def export_csv(self) -> Path:
        """Write provenance.csv atomically: spans, then claim verdicts (REP-3).

        Raises if the file is locked (open in Excel)."""
        tmp = self.csv_path.with_suffix(f".{os.getpid()}.tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, CSV_FIELDS, restval="")
            writer.writeheader()
            for span in self.spans():
                writer.writerow({"kind": "span", **{c: getattr(span, c) or "" for c in SPAN_FIELDS}})
            for claim in self.claims():
                writer.writerow({
                    "kind": "claim", "claim_id": claim.claim_id, "turn": claim.turn,
                    "text": claim.text, "verdict": claim.verdict,
                    "span_ids": "; ".join(claim.span_ids),
                    "dropped_qualifiers": "; ".join(claim.dropped_qualifiers),
                    "decided_by": claim.decided_by, "confidence": f"{claim.confidence:.2f}",
                    "critical": "yes" if claim.critical else "no",
                })
        os.replace(tmp, self.csv_path)
        return self.csv_path
