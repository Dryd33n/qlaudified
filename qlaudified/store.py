"""Session ledger: SQLite (WAL, busy timeout) is the source of truth; provenance.csv is its rolling,
read-only view (design revision 2).

The ledger holds **facts, never passages**: one row per critical fact (a sentence or line with a
number, date or qualifier) that Claude read or stated, with its provenance fields (REQ-3.2). What
Claude read is logged in ``sources`` (path or URL, lines, content hash; no text), so a source can
be re-read later and checked for changes. Steps count tool calls per session. Several hook
processes write at once (parallel tool calls), so every write is one short ``BEGIN IMMEDIATE``
transaction, and the CSV is rewritten under the same lock.

Layout per session: index.sqlite, provenance.csv, claims.csv, consults.jsonl,
reports/turn-<n>.{md,json}, usage.jsonl, timings.jsonl.
"""

import contextlib
import csv
import os
import sqlite3
import stat
import time
from pathlib import Path

from qlaudified.paths import ensure_gitignore
from qlaudified.records import asdict, fields, record

TEXT_CAP = 600  # a fact is one sentence or line; anything longer is cut


@record
class Span:
    """One fact row. Named Span for continuity with revision 1; ``Fact`` is the same class."""

    span_id: str  # "F14"
    origin: str  # how it was read: local-doc | code | command-output | web-raw | web-summary |
    #              search-snippet | mcp | user-prompt | claude
    source: str  # project-relative path, URL, "mcp:<server>/<tool>", "prompt" or "claude"
    locator: str  # "L22", "p7", "turn 2" or "step 5"
    text: str  # the critical claim (REQ-3.2: description)
    numbers: str = ""  # normalized values and dates
    qualifiers: str = ""  # qualifiers in the original source (REQ-3.2)
    derived_from: str | None = None
    agent_id: str = "main"
    turn: str | None = None  # prompt_id
    ts: str = ""
    hash: str = ""
    category: str = ""  # REQ-3.2 origin: Direct Retrieved Fact | Provided Document | Internal
    #                    Document | User Prompt | Model Inference | Training Data | Hybrid
    step: int = 0  # the tool call that brought it in
    first_use_step: int | None = None
    first_use_qualifiers: str | None = None  # qualifiers present at first use ("" = none)
    uses: str = ""  # "5:Write notes.md; 9:Bash calc.py"
    primary_source: str = ""  # hybrids: the fact that mainly drove it
    sources_agree: str = ""  # hybrids: yes | no
    impact: str = ""  # operational impact (REQ-3.2)


Fact = Span


@record
class Claim:
    claim_id: str  # "C2.1": turn 2, first claim
    turn: str  # prompt_id
    text: str
    span_ids: list[str]  # fact IDs
    # supported | partial | qualifier-dropped | contradicted | unsupported | inference |
    # unresolved | not-checked | source-changed
    verdict: str
    dropped_qualifiers: list[str]
    decided_by: str  # deterministic | nli | llm | reread | none
    confidence: float
    critical: bool


@record
class Turn:
    n: int
    prompt_id: str
    answer: str
    ts: str


SPAN_FIELDS = list(fields(Span))
CLAIM_FIELDS = list(fields(Claim))
# provenance.csv as Claude and people see it: REQ-3.2 columns first.
CSV_COLUMNS = [
    ("fact_id", "span_id"), ("claim", "text"), ("value", "numbers"), ("origin", "category"),
    ("source", "source"), ("locator", "locator"), ("source_qualifiers", "qualifiers"),
    ("first_use_step", "first_use_step"), ("first_use_qualifiers", "first_use_qualifiers"),
    ("uses", "uses"), ("primary_source", "primary_source"), ("sources_agree", "sources_agree"),
    ("operational_impact", "impact"), ("read_as", "origin"), ("agent_id", "agent_id"),
    ("step", "step"), ("turn", "turn"), ("ts", "ts"),
]
CLAIM_CSV = ["claim_id", "turn", "text", "verdict", "fact_ids", "dropped_qualifiers",
             "decided_by", "confidence", "critical"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    span_id TEXT UNIQUE, origin TEXT, source TEXT, locator TEXT, text TEXT, numbers TEXT,
    qualifiers TEXT, derived_from TEXT, agent_id TEXT, turn TEXT, ts TEXT, hash TEXT,
    category TEXT, step INTEGER, first_use_step INTEGER, first_use_qualifiers TEXT, uses TEXT,
    primary_source TEXT, sources_agree TEXT, impact TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS spans_same_fact ON spans(source, locator, hash, agent_id);
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY, turn TEXT, text TEXT, span_ids TEXT, verdict TEXT,
    dropped_qualifiers TEXT, decided_by TEXT, confidence REAL, critical INTEGER
);
CREATE TABLE IF NOT EXISTS turns (
    n INTEGER PRIMARY KEY AUTOINCREMENT, prompt_id TEXT UNIQUE, answer TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    n INTEGER PRIMARY KEY AUTOINCREMENT, tool_use_id TEXT UNIQUE, tool TEXT, agent_id TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS sources (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, locator TEXT, hash TEXT, origin TEXT,
    rereadable TEXT, agent_id TEXT, turn TEXT, step INTEGER, ts TEXT,
    UNIQUE (source, locator, hash, agent_id)
);
CREATE TABLE IF NOT EXISTS provided (source TEXT PRIMARY KEY, turn TEXT);
"""


@record
class Source:
    source: str
    locator: str
    hash: str
    origin: str
    rereadable: str  # file | web | no
    agent_id: str = "main"
    turn: str | None = None
    step: int = 0


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Store:
    def __init__(self, session_dir) -> None:
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        ensure_gitignore(self.session_dir.parent.parent)
        self.db_path = self.session_dir / "index.sqlite"
        self.csv_path = self.session_dir / "provenance.csv"
        self.claims_path = self.session_dir / "claims.csv"
        self._con: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        """One connection per Store, opened on first use: a hook call makes ~10 ledger calls,
        and reopening (WAL and schema checks included) cost ~30 ms of the step (Sprint 5)."""
        if self._con is None:
            self._con = self._open()
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def _open(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        con.execute("PRAGMA busy_timeout = 10000")
        # Switching to WAL and creating the schema ignore the busy timeout, and parallel hooks
        # race to do both on a new database, so retry them; skip them once done.
        for attempt in range(200):
            try:
                if con.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                    con.execute("PRAGMA journal_mode = WAL")
                if not con.execute("SELECT 1 FROM sqlite_master WHERE name = 'provided'").fetchone():
                    con.executescript(SCHEMA)
                return con
            except sqlite3.OperationalError as e:
                if "locked" not in str(e) and "busy" not in str(e) or attempt == 199:
                    con.close()
                    raise
                time.sleep(0.01 + 0.0002 * attempt)
        return con

    @contextlib.contextmanager
    def _write(self):
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise

    def _query(self, sql: str, args: tuple = ()) -> list[tuple]:
        return self._connect().execute(sql, args).fetchall()

    # --- facts -------------------------------------------------------------------------------

    def add_span(self, span: Span) -> str:
        return self.add_spans([span])[0]

    def add_spans(self, spans: list[Span]) -> list[str]:
        """Store facts and return their IDs. A fact the same agent saw before keeps its first ID;
        a subagent reading it gets its own row, since its context is separate."""
        return [span_id for span_id, _ in self._insert(spans)]

    def add_new_spans(self, spans: list[Span]) -> list[Span]:
        """Store facts and return only those this agent hadn't seen: the delta to refeed."""
        return [span for span, (_, new) in zip(spans, self._insert(spans), strict=True) if new]

    def _insert(self, spans: list[Span]) -> list[tuple[str, bool]]:
        out = []
        cols = [c for c in SPAN_FIELDS if c != "span_id"]
        with self._write() as con:
            for span in spans:
                row = asdict(span)
                row["ts"] = row["ts"] or _now()
                row["text"] = row["text"][:TEXT_CAP]
                cur = con.execute(
                    f"INSERT OR IGNORE INTO spans ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' for _ in cols)})", [row[c] for c in cols])
                new = cur.rowcount == 1
                if new:
                    span_id = f"F{cur.lastrowid}"
                    con.execute("UPDATE spans SET span_id = ? WHERE seq = ?", (span_id, cur.lastrowid))
                else:
                    span_id = con.execute(
                        "SELECT span_id FROM spans "
                        "WHERE source = ? AND locator = ? AND hash = ? AND agent_id = ?",
                        (row["source"], row["locator"], row["hash"], row["agent_id"]),
                    ).fetchone()[0]
                span.span_id = span_id
                out.append((span_id, new))
        return out

    def spans(self, with_numbers: bool = False) -> list[Span]:
        where = " WHERE numbers != ''" if with_numbers else ""
        rows = self._query(f"SELECT {', '.join(SPAN_FIELDS)} FROM spans{where} ORDER BY seq")
        return [Span(**dict(zip(SPAN_FIELDS, r, strict=True))) for r in rows]

    facts = spans

    def update_fact(self, span_id: str, **values) -> None:
        unknown = set(values) - set(SPAN_FIELDS)
        if unknown:
            raise ValueError(f"unknown fact fields: {sorted(unknown)}")
        with self._write() as con:
            con.execute(f"UPDATE spans SET {', '.join(f'{k} = ?' for k in values)} "
                        "WHERE span_id = ?", (*values.values(), span_id))

    def delete_fact(self, span_id: str) -> None:
        """The sidecar judged a candidate trivial (a version number, a step count)."""
        with self._write() as con:
            con.execute("DELETE FROM spans WHERE span_id = ?", (span_id,))

    def append_impact(self, span_id: str, note: str) -> None:
        """Operational impact grows as a fact is used (PROV-5)."""
        with self._write() as con:
            row = con.execute("SELECT impact FROM spans WHERE span_id = ?", (span_id,)).fetchone()
            if row is not None:
                impact = f"{row[0]}; {note}" if row[0] else note
                con.execute("UPDATE spans SET impact = ? WHERE span_id = ?", (impact, span_id))

    def set_derived_from(self, span_id: str, value: str) -> None:
        """Link a WebFetch summary fact to its page, or mark it ``summarized-only`` (CAP-3, 4)."""
        self.update_fact(span_id, derived_from=value)

    def record_use(self, span_id: str, step: int, where: str, qualifiers: str) -> bool:
        """Note that a fact was used at ``step``; the first use also keeps the qualifiers present
        then (PROV-4). Returns True for the first use."""
        with self._write() as con:
            row = con.execute("SELECT first_use_step, uses FROM spans WHERE span_id = ?",
                              (span_id,)).fetchone()
            if row is None:
                return False
            first, uses = row
            entry = f"{step}:{where}"
            if entry in (uses or "").split("; "):
                return False
            uses = f"{uses}; {entry}" if uses else entry
            if first is None:
                con.execute("UPDATE spans SET uses = ?, first_use_step = ?, first_use_qualifiers = ? "
                            "WHERE span_id = ?", (uses, step, qualifiers, span_id))
                return True
            con.execute("UPDATE spans SET uses = ? WHERE span_id = ?", (uses, span_id))
            return False

    def sidecar_qualifiers(self) -> list[str]:
        """Qualifiers on facts that the base lexicon doesn't know (sidecar finds): an extra
        lexicon class when verifying."""
        from qlaudified.lexicon import HEDGES

        known = {w for words in HEDGES.values() for w in words}
        rows = self._query("SELECT qualifiers FROM spans WHERE qualifiers != ''")
        return sorted({w for (q,) in rows for w in q.split("; ") if w and w not in known})

    # --- steps, sources, provided files ------------------------------------------------------

    def next_step(self, tool_use_id: str, tool: str, agent_id: str = "main") -> int:
        """The step number of this tool call (1, 2, ...); the same call always gets the same n."""
        with self._write() as con:
            con.execute("INSERT OR IGNORE INTO steps (tool_use_id, tool, agent_id, ts) "
                        "VALUES (?, ?, ?, ?)", (tool_use_id, tool, agent_id, _now()))
            return con.execute("SELECT n FROM steps WHERE tool_use_id = ?",
                               (tool_use_id,)).fetchone()[0]

    def current_step(self) -> int:
        rows = self._query("SELECT MAX(n) FROM steps")
        return rows[0][0] or 0

    def add_sources(self, sources: list[Source]) -> None:
        cols = list(fields(Source))
        with self._write() as con:
            con.executemany(
                f"INSERT OR IGNORE INTO sources ({', '.join(cols)}, ts) "
                f"VALUES ({', '.join('?' for _ in cols)}, ?)",
                [(*(getattr(s, c) for c in cols), _now()) for s in sources])

    def sources(self) -> list[Source]:
        cols = list(fields(Source))
        rows = self._query(f"SELECT {', '.join(cols)} FROM sources ORDER BY seq")
        return [Source(*r) for r in rows]

    def add_provided(self, paths: list[str], turn: str | None) -> None:
        with self._write() as con:
            con.executemany("INSERT OR IGNORE INTO provided (source, turn) VALUES (?, ?)",
                            [(p, turn) for p in paths])

    def provided(self) -> set[str]:
        return {r[0] for r in self._query("SELECT source FROM provided")}

    # --- turns and claims --------------------------------------------------------------------

    def start_turn(self, prompt_id: str, answer: str) -> Turn:
        """Record a turn's final answer; a second Stop in the same turn updates it and keeps its n."""
        ts = _now()
        with self._write() as con:
            con.execute(
                "INSERT INTO turns (prompt_id, answer, ts) VALUES (?, ?, ?) ON CONFLICT(prompt_id) "
                "DO UPDATE SET answer = excluded.answer, ts = excluded.ts", (prompt_id, answer, ts))
            n = con.execute("SELECT n FROM turns WHERE prompt_id = ?", (prompt_id,)).fetchone()[0]
        return Turn(n, prompt_id, answer, ts)

    def last_turn(self) -> Turn | None:
        rows = self._query("SELECT n, prompt_id, answer, ts FROM turns ORDER BY n DESC LIMIT 1")
        return Turn(*rows[0]) if rows else None

    def add_claims(self, turn: str, claims: list[Claim]) -> None:
        """Replace the turn's claims, so a re-verified turn keeps no stale verdicts."""
        with self._write() as con:
            con.execute("DELETE FROM claims WHERE turn = ?", (turn,))
            con.executemany(
                f"INSERT INTO claims ({', '.join(CLAIM_FIELDS)}) "
                f"VALUES ({', '.join('?' for _ in CLAIM_FIELDS)})",
                [(c.claim_id, c.turn, c.text, "; ".join(c.span_ids), c.verdict,
                  "; ".join(c.dropped_qualifiers), c.decided_by, c.confidence, int(c.critical))
                 for c in claims])

    def claims(self, turn: str | None = None) -> list[Claim]:
        where, args = (" WHERE c.turn = ?", (turn,)) if turn is not None else ("", ())
        rows = self._query(
            f"SELECT {', '.join('c.' + f for f in CLAIM_FIELDS)} FROM claims c "
            f"LEFT JOIN turns t ON t.prompt_id = c.turn{where} ORDER BY t.n, c.rowid", args)
        out = []
        for r in rows:
            c = Claim(**dict(zip(CLAIM_FIELDS, r, strict=True)))
            c.span_ids = [s for s in str(c.span_ids or "").split("; ") if s]
            c.dropped_qualifiers = [s for s in str(c.dropped_qualifiers or "").split("; ") if s]
            c.critical = bool(c.critical)
            out.append(c)
        return out

    # --- the CSV views -----------------------------------------------------------------------

    def export_csv(self) -> Path:
        """Rewrite provenance.csv (facts, REQ-3.2 columns) and claims.csv from the ledger.

        provenance.csv is read-only on disk, so Claude's Write and Edit fail on it; this is the
        only writer, under the database lock, so parallel hooks never interleave. Any other
        change to the file is undone here (PROV-7)."""
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")  # serializes rewrites across hook processes
            self._write_csv(self.csv_path, [h for h, _ in CSV_COLUMNS],
                            ({h: _cell(getattr(s, attr)) for h, attr in CSV_COLUMNS}
                             for s in self.spans()))
            self._write_csv(self.claims_path, CLAIM_CSV, (
                {"claim_id": c.claim_id, "turn": c.turn, "text": c.text, "verdict": c.verdict,
                 "fact_ids": "; ".join(c.span_ids),
                 "dropped_qualifiers": "; ".join(c.dropped_qualifiers),
                 "decided_by": c.decided_by, "confidence": f"{c.confidence:.2f}",
                 "critical": "yes" if c.critical else "no"} for c in self.claims()))
            con.execute("COMMIT")
        finally:
            if con.in_transaction:
                con.execute("ROLLBACK")
        return self.csv_path

    @staticmethod
    def _write_csv(path: Path, header: list[str], rows) -> None:
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, header, restval="")
            writer.writeheader()
            writer.writerows(rows)
        if path.exists():
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)  # Windows can't replace a read-only file
        os.replace(tmp, path)
        os.chmod(path, stat.S_IREAD)


def _cell(value) -> str:
    """One physical line per row: facts are single sentences, but keep the CSV line-safe."""
    return "" if value is None else " ".join(str(value).split())
