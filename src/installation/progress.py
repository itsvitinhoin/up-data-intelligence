"""Logical progress and evidence-based serial ETA; publications have no data weight."""

from collections import Counter, defaultdict
from statistics import median

from src.installation.model import ACTIVE, AMBIGUOUS, Row


def summarize(rows: list[Row]) -> Row:
    required = [r for r in rows if r["required"]]
    completed = sum(r["status"] == "COMPLETE" for r in required)
    groups: dict[tuple[str, str, str], list[Row]] = defaultdict(list)
    for row in required:
        groups[row["source"], row["resource"], row["unit_kind"]].append(row)
    eta: float | None = 0
    for group in groups.values():
        left = sum(r["status"] != "COMPLETE" for r in group)
        if not left:
            continue
        samples = sorted(
            (r for r in group if r["status"] == "COMPLETE" and r["duration_seconds"] > 0),
            key=lambda r: (r.get("finished_at") or "", r["work_unit_id"]),
        )[-10:]
        if len(samples) < 3:
            eta = None
            break
        eta = (eta or 0) + left * median(r["duration_seconds"] for r in samples)
    counts = Counter(r["status"] for r in rows)
    return {
        "progress": {
            "kind": "CHUNKS" if required else "UNKNOWN",
            "processed": completed if required else None,
            "total": len(required) or None,
            "percent": completed / len(required) * 100 if required else None,
            "eta_seconds": eta if required else None,
        },
        "work": {
            "pending": counts["PENDING"] + counts["DEFERRED"],
            "running": sum(counts[s] for s in ACTIVE - AMBIGUOUS),
            "complete": counts["COMPLETE"],
            "blocked": counts["BLOCKED"],
            "ambiguous": sum(counts[s] for s in AMBIGUOUS),
        },
        "records_processed": sum(r["records_processed"] for r in rows),
        "pages_processed": sum(r["pages_processed"] for r in rows),
    }


def plan_state(rows: list[Row], *, publication_valid: bool, final_valid: bool) -> str:
    if any(r["status"] in AMBIGUOUS for r in rows):
        return "OUTCOME_UNKNOWN"
    if any(r["status"] == "BLOCKED" for r in rows):
        return "BLOCKED"
    if (
        all(r["status"] == "COMPLETE" for r in rows if r["required"])
        and final_valid
        and not any(r["status"] != "COMPLETE" for r in rows)
    ):
        return "COMPLETE"
    return "PARTIAL" if publication_valid else "RUNNING"
