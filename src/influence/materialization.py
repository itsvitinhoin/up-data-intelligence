"""Local atomic publication of all four proposed models, no BigQuery transport."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from src.analytics.engine import Row, instant
from src.analytics.policy import Policy
from src.influence.engine import InfluenceScope, build
from src.influence.schema import SCHEMAS
from src.utils.data import canonical, digest, numeric, timestamp

VERSION = "influence-timeline-2.0.0"


def encode(tables: dict[str, list[Row]]) -> dict[str, list[Row]]:
    if set(tables) != set(SCHEMAS):
        raise ValueError("influence_model_set_incomplete")
    result = {}
    for name, rows in tables.items():
        fields = SCHEMAS[name].fields
        if len({(r.get("store_id"), r.get("row_key")) for r in rows}) != len(rows):
            raise ValueError("duplicate_materialized_grain")
        encoded = []
        for row in rows:
            if set(row) != set(fields):
                raise ValueError("influence_output_schema_mismatch")
            record = dict(row)
            for field, typ in fields.items():
                v = row[field]
                if v is None:
                    if field in {"row_key", "store_id"}:
                        raise ValueError("missing_materialized_key")
                    continue
                if typ == "NUMERIC":
                    record[field] = numeric(v)
                elif typ == "TIMESTAMP":
                    record[field] = timestamp(v)
                elif typ == "STRING" and not isinstance(v, str):
                    raise ValueError("invalid_materialized_string")
                elif typ == "BOOL" and type(v) is not bool:
                    raise ValueError("invalid_materialized_boolean")
                elif typ == "INT64" and (type(v) is not int or not -(2**63) <= v < 2**63):
                    raise ValueError("invalid_materialized_integer")
                elif typ == "JSON":
                    canonical(v)
            encoded.append(record)
        result[name] = encoded
    return result


def materialize(
    policy: Policy,
    snapshot: dict[str, Any],
    *,
    calculated_at: str,
    influence_scope: InfluenceScope | str = InfluenceScope.LIFETIME,
) -> Row:
    scope = InfluenceScope(influence_scope)
    tables = encode(build(policy, **snapshot, calculated_at=calculated_at, influence_scope=scope))
    # Coherent local input hash, NOT a live CORE commit watermark or CDC generation.
    sources = {
        name: sorted(
            [r for r in snapshot[name] if r.get("store_id") == policy.store_id], key=canonical
        )
        for name in ("customers", "orders", "events", "identity_links")
    }
    source_hash = digest(sources)
    counts = {name: len(rows) for name, rows in tables.items()}
    selected_facts = sum(
        instant(e["occurred_at"]) < instant(policy.as_of) for e in sources["events"]
    )
    resolved_facts = sum(r["record_type"] == "FACT" for r in tables["analytics_customer_timeline"])
    receipt = {
        "layer_version": VERSION,
        "store_id": policy.store_id,
        "policy_hash": policy.key,
        "source_snapshot_hash": source_hash,
        "report_from": policy.report_from,
        "report_to": policy.report_to,
        "history_complete": policy.history_complete,
        "facts_complete": policy.facts_complete,
        "as_of": timestamp(policy.as_of),
        "calculated_at": timestamp(calculated_at),
        "influence_scope": scope.value,
        "model_counts": counts,
        "unresolved_facts": selected_facts - resolved_facts,
        "content_sha256": digest(tables),
        "status": "completed_offline",
    }
    receipt["publication_id"] = digest(receipt)
    return {"tables": tables, "receipt": receipt}


def publish_local(path: Path, artifact: Row) -> bool:
    """All-or-nothing visibility via same-filesystem hard link; no overwrite or cloud IO.

    Returns False on an identical retry; different contents fail without replacing anything.
    """
    payload = (canonical(artifact) + "\n").encode()
    if path.exists():
        if path.read_bytes() == payload:
            return False
        raise FileExistsError("offline_publication_conflict")
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".influence-", delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() == payload:
                return False
            raise FileExistsError("offline_publication_conflict") from None
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
