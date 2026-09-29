"""Batch-scoped deterministic Fact -> Meta lookup; no name matching or identity merging."""

from typing import Any

from src.bigquery.repository import Repository
from src.connectors.meta.config import Account, meta_id, validate_accounts
from src.domain.models import SafeError
from src.utils.data import digest

ENTITY_FIELDS = {"ad_id": "meta_ads", "adset_id": "meta_adsets", "campaign_id": "meta_campaigns"}
TOUCHPOINT_FIELDS = "store_id fact_id event_id visitor_id session_id anonymous_id user_id occurred_at fbclid fbc fbp utm_source utm_medium utm_campaign utm_content utm_term landing_url referrer".split()


def resolve_facts(
    facts: list[dict[str, Any]], repo: Repository, accounts: tuple[Account, ...]
) -> list[dict[str, Any]]:
    validate_accounts(accounts)
    if len(facts) > 1000:
        raise SafeError("meta_fact_lookup_requires_bounded_batches")
    if any(
        f.get("source_system") != "upzero" or not f.get("fact_id") or not f.get("store_id")
        for f in facts
    ):
        raise SafeError("meta_fact_lookup_scope_invalid")
    output = []
    for store in sorted({f["store_id"] for f in facts}):
        allowed = {a.account_id for a in accounts if a.store_id == store}
        local = [f for f in facts if f["store_id"] == store]
        indexes: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for field, table in ENTITY_FIELDS.items():
            ids = sorted({str(f["meta_" + field]) for f in local if f.get("meta_" + field)})
            index: dict[str, list[dict[str, Any]]] = {}
            for row in repo.find(table, store, field, ids) if ids else []:
                if (
                    row["store_id"] == store
                    and row["account_id"] in allowed
                    and row.get("source_system") == "meta"
                ):
                    index.setdefault(row[field], []).append(row)
            indexes[field] = index
        for fact in local:
            point: dict[str, Any] = {f: fact.get(f) for f in TOUCHPOINT_FIELDS}
            point.update(
                source_system="upzero",
                source_fact_version_id=fact.get("version_id"),
                account_id=None,
                confidence="none",
                evidence_type="no_meta_id",
                attribution_eligible=False,
                entity_versions={},
                issues=[],
            )
            candidates: dict[str, list[dict[str, Any]]] = {}
            invalid = False
            for field in ENTITY_FIELDS:
                value = fact.get("meta_" + field)
                point[field] = value
                if value is None:
                    continue
                try:
                    meta_id(value)
                except SafeError:
                    point["issues"].append("invalid_meta_id")
                    invalid = True
                    continue
                candidates[field] = indexes[field].get(value, [])
                if not candidates[field]:
                    point["issues"].append(
                        "fact_" + field + "_without_meta_" + field.removesuffix("_id")
                    )
            groups = [{r["account_id"] for r in rows} for rows in candidates.values() if rows]
            common = set.intersection(*groups) if groups else set()
            if candidates:
                point["evidence_type"] = "unresolved_meta_ids"
            if groups and (len(common) != 1 or invalid):
                point["evidence_type"] = "ambiguous_or_conflicting_meta_account"
            elif common and not invalid:
                account_id = next(iter(common))
                matched = {
                    field: [r for r in rows if r["account_id"] == account_id]
                    for field, rows in candidates.items()
                }
                conflicts = any(len(rows) > 1 for rows in matched.values())
                for rows in matched.values():
                    for row in rows:
                        for parent in ("campaign_id", "adset_id"):
                            observed = fact.get("meta_" + parent)
                            if (
                                observed is not None
                                and row.get(parent) is not None
                                and observed != row[parent]
                            ):
                                conflicts = True
                if conflicts:
                    point["evidence_type"] = "conflicting_meta_hierarchy"
                else:
                    point.update(
                        account_id=account_id,
                        confidence="deterministic_entity_match",
                        evidence_type="configured_account_and_exact_source_ids",
                    )
                    point["entity_versions"] = {
                        field: rows[0]["version_id"] for field, rows in matched.items() if rows
                    }
                    # Candidate evidence only, not a conversion assignment or human identity.
                    point["attribution_eligible"] = not point["issues"]
            point["touchpoint_id"] = digest(
                [store, "upzero", fact.get("fact_id"), fact.get("version_id")]
            )
            output.append(point)
    return output
