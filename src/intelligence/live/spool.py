"""Execution-local private SQLite row/anchor spool. No remote IO or persistent cache."""

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from src.analytics.engine import Row, instant
from src.influence.identity import IDENTITY_EVIDENCE_CONTRACT_VERSION, resolver_evidence, value
from src.utils.data import canonical


def primitive(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {k: primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    return value


def clock(at: str) -> str:
    return instant(at).isoformat(timespec="microseconds")


class Rows:
    def __init__(self, spool: "Spool", name: str):
        self.spool, self.name = spool, name

    def __len__(self) -> int:
        return int(
            self.spool.db.execute(
                "SELECT COUNT(*) FROM rows WHERE name=?", (self.name,)
            ).fetchone()[0]
        )

    def __iter__(self) -> Iterator[Row]:
        order = (
            "at,fact,row_key"
            if self.name == "paid"
            else "customer,at,row_key"
            if self.name == "timeline"
            else "json_extract(sorter,'$[0]'),json_extract(sorter,'$[1]'),row_key"
            if self.name.startswith("orders:")
            else "sorter,row_key"
        )
        for (data,) in self.spool.db.execute(
            "SELECT data FROM rows WHERE name=? ORDER BY " + order, (self.name,)
        ):
            yield json.loads(data)

    def append(self, row: Row) -> None:
        self.spool.put(self.name, row)

    def get(self, key: str) -> Row:
        result = self.spool.db.execute(
            "SELECT data FROM rows WHERE name=? AND row_key=?", (self.name, key)
        ).fetchone()
        if result is None:
            raise KeyError(key)
        return json.loads(result[0])  # type: ignore[no-any-return]

    def content_hash(self, *, omit_generation: bool = False) -> str:
        h = hashlib.sha256(b"intelligence-content:v2\0")
        for row in self:
            frame(h, {k: v for k, v in row.items() if not (omit_generation and k == "generation")})
        return h.hexdigest()


def frame(h: Any, value: Any) -> None:
    data = canonical(value).encode()
    h.update(len(data).to_bytes(8, "big"))
    h.update(data)


class Spool:
    def __init__(self) -> None:
        self.directory = TemporaryDirectory(prefix="up-intelligence-")
        self.path = Path(self.directory.name) / "spool.sqlite"
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            self.db = sqlite3.connect(self.path)
            self.db.executescript("""
                PRAGMA journal_mode=OFF;
                PRAGMA temp_store=FILE;
                PRAGMA cache_size=-2048;
                PRAGMA mmap_size=0;
                CREATE TABLE rows(name TEXT NOT NULL,row_key TEXT NOT NULL,sorter TEXT NOT NULL,
                  customer TEXT,at TEXT,fact TEXT,data TEXT NOT NULL,PRIMARY KEY(name,row_key));
                CREATE INDEX customer_rows ON rows(name,customer,at,row_key);
                CREATE INDEX fact_rows ON rows(name,fact);
                CREATE TABLE anchors(field TEXT,token TEXT,kind TEXT,customer TEXT,fact TEXT,data TEXT,
                  PRIMARY KEY(field,token,kind,fact));
                CREATE TABLE owners(field TEXT,token TEXT,customer TEXT,PRIMARY KEY(field,token,customer));
                CREATE TABLE evidence_links(source_fact_id TEXT NOT NULL,link_id TEXT NOT NULL PRIMARY KEY,data TEXT NOT NULL);
                CREATE INDEX evidence_source_fact ON evidence_links(source_fact_id,link_id);
                CREATE TABLE matches(scope TEXT,oid TEXT,campaign TEXT,fact TEXT,at TEXT,data TEXT,
                  PRIMARY KEY(scope,oid,campaign,fact));
            """)
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.directory.cleanup()
            raise

    def __enter__(self) -> "Spool":
        return self

    def __exit__(self, *args: Any) -> None:
        try:
            self.db.close()
        finally:
            self.directory.cleanup()

    def rows(self, name: str) -> Rows:
        return Rows(self, name)

    def put(
        self, name: str, row: Row, *, key: str | None = None, sorter: str | None = None
    ) -> None:
        row = primitive(row)
        data = canonical(row)
        # Output has an existing single-row staging bound; sources use transport bounds.
        if not name.startswith("source:") and len(data.encode()) + 2 > 500000:
            raise ValueError("intelligence_row_too_large")
        at = clock(row["occurred_at"]) if row.get("occurred_at") else None
        try:
            self.db.execute(
                "INSERT INTO rows VALUES(?,?,?,?,?,?,?)",
                (
                    name,
                    key or row["row_key"],
                    sorter or row["row_key"],
                    row.get("customer_id"),
                    at,
                    row.get("fact_id"),
                    data,
                ),
            )
        except sqlite3.IntegrityError:
            raise ValueError("duplicate_intelligence_grain") from None

    def source_hash(
        self, sources: Mapping[str, list[Row]], *, events: str = "source:events"
    ) -> str:
        if set(sources) != {"customers", "orders", "items"}:
            raise ValueError("intelligence_source_set_incomplete")
        h = hashlib.sha256(b"source_snapshot_hash:v3\0")
        frame(h, {"identity_evidence_contract_version": IDENTITY_EVIDENCE_CONTRACT_VERSION})
        for name in sorted({*sources, "events", "identity_evidence"}):
            frame(h, name)
            count = 0
            iterator = (
                (
                    json.loads(data)
                    for (data,) in self.db.execute(
                        "SELECT data FROM evidence_links ORDER BY source_fact_id,link_id"
                    )
                )
                if name == "identity_evidence"
                else iter(self.rows(events))
                if name == "events"
                else iter(sorted(sources[name], key=canonical))
            )
            for row in iterator:
                frame(h, row)
                count += 1
            frame(h, count)
        return h.hexdigest()


class DiskAnchors:
    maximum_path_bytes: int | None = 500000

    def __init__(self, spool: Spool):
        self.spool = spool
        self.sealed = False

    def add(self, anchor: Row) -> None:
        if self.sealed:
            raise ValueError("identity_context_is_immutable")
        for field in ("session_id", "visitor_id", "user_id"):
            if token := value(anchor["fact"], field):
                try:
                    self.spool.db.execute(
                        "INSERT INTO anchors VALUES(?,?,?,?,?,?)",
                        (
                            field,
                            token,
                            anchor["kind"],
                            anchor["customer"],
                            anchor["fact"]["fact_id"],
                            canonical(anchor),
                        ),
                    )
                    self.spool.db.execute(
                        "INSERT OR IGNORE INTO owners VALUES(?,?,?)",
                        (field, token, anchor["customer"]),
                    )
                except sqlite3.IntegrityError:
                    raise ValueError("duplicate_or_invalid_fact_key") from None

    def find(self, field: str, token: str, kind: str) -> Iterator[Row]:
        for (data,) in self.spool.db.execute(
            "SELECT data FROM anchors WHERE field=? AND token=? AND kind=? ORDER BY fact",
            (field, token, kind),
        ):
            yield json.loads(data)

    def owner_count(self, field: str, token: str) -> int:
        return len(
            self.spool.db.execute(
                "SELECT customer FROM owners WHERE field=? AND token=? LIMIT 2", (field, token)
            ).fetchall()
        )

    def seal(self) -> None:
        self.spool.db.commit()
        self.sealed = True


class PaidLookup(Mapping[str, Row]):
    def __init__(self, spool: Spool):
        self.rows = spool.rows("paid")

    def __getitem__(self, key: str) -> Row:
        result = self.rows.spool.db.execute(
            "SELECT data FROM rows WHERE name='paid' AND fact=?", (key,)
        ).fetchone()
        if result is None:
            raise KeyError(key)
        return json.loads(result[0])  # type: ignore[no-any-return]

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[str]:
        for (fid,) in self.rows.spool.db.execute(
            "SELECT fact FROM rows WHERE name='paid' ORDER BY fact"
        ):
            yield fid


class DiskEvidenceIndex:
    """Private sealed index; no remote IO and no per-Fact Python link list."""

    def __init__(
        self, spool: Spool, *, store_id: str, history_from: str, as_of: str, calculated_at: str
    ):
        self.spool, self.store_id = spool, store_id
        self.history_from, self.as_of, self.calculated_at = map(
            instant, (history_from, as_of, calculated_at)
        )
        self.sealed = False

    def add(self, row: Row) -> None:
        if self.sealed:
            raise ValueError("identity_evidence_is_immutable")
        if (
            not resolver_evidence(row)
            or not value(row, "link_id")
            or not value(row, "source_fact_id")
            or row.get("source_version_id") is None
            or row.get("occurred_at") is None
        ):
            raise ValueError("duplicate_or_invalid_identity_evidence")
        if (
            row.get("store_id") != self.store_id
            or row.get("source_system") != "upzero"
            or not self.history_from <= instant(row["occurred_at"]) < self.as_of
        ):
            raise ValueError("identity_evidence_scope_mismatch")
        if row.get("observed_at") and instant(row["observed_at"]) > self.calculated_at:
            raise ValueError("snapshot_observation_after_calculation")
        try:
            self.spool.db.execute(
                "INSERT INTO evidence_links VALUES(?,?,?)",
                (
                    row["source_fact_id"],
                    row["link_id"],
                    canonical(primitive(row)),
                ),
            )
        except sqlite3.IntegrityError:
            raise ValueError("duplicate_or_invalid_identity_evidence") from None

    def seal(self) -> None:
        self.spool.db.commit()
        self.sealed = True

    def links_for(self, source_fact_id: str) -> Iterator[Mapping[str, Any]]:
        if not self.sealed:
            raise ValueError("identity_evidence_not_sealed")
        for (data,) in self.spool.db.execute(
            "SELECT data FROM evidence_links WHERE source_fact_id=? ORDER BY link_id",
            (source_fact_id,),
        ):
            yield json.loads(data)
