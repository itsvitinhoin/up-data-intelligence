"""Explicit operational drift allowlist; never authorizes planned resource updates."""

from typing import Any

Path = tuple[str | int, ...]
_MISSING = object()
_SUPPORTED = frozenset(
    {
        "google_bigquery_table",
        "google_cloud_run_v2_job",
        "google_project_iam_member",
        "google_bigquery_table_iam_member",
        "google_secret_manager_secret",
        "google_secret_manager_secret_iam_member",
        "google_storage_bucket",
        "google_storage_bucket_iam_member",
    }
)
_BIGQUERY = frozenset({("etag",), ("last_modified_time",), ("num_bytes",), ("num_rows",)})
_BIGQUERY_EMPTY_MAPS = frozenset({("labels",), ("resource_tags",)})
_SECRET_EMPTY_MAPS = frozenset({("annotations",), ("version_aliases",)})
_IAM_ETAGS = frozenset(
    {
        "google_bigquery_table_iam_member",
        "google_secret_manager_secret_iam_member",
        "google_storage_bucket_iam_member",
    }
)
_EMPTY_MAPS = frozenset(
    {("annotations",), ("labels",), ("template", 0, "annotations"), ("template", 0, "labels")}
)


def changed_paths(before: Any, after: Any, path: Path = ()) -> list[Path]:
    """Stable structural diff, preserving missing/null and list membership differences."""
    if type(before) is not type(after):
        return [path]
    if isinstance(before, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            result.extend(
                changed_paths(before.get(key, _MISSING), after.get(key, _MISSING), (*path, key))
            )
        return result
    if isinstance(before, list):
        result = []
        for index in range(max(len(before), len(after))):
            result.extend(
                changed_paths(
                    before[index] if index < len(before) else _MISSING,
                    after[index] if index < len(after) else _MISSING,
                    (*path, index),
                )
            )
        return result
    return [] if before == after else [path]


def value_at(value: Any, path: Path) -> Any:
    for part in path:
        if isinstance(part, str) and isinstance(value, dict) and part in value:
            value = value[part]
        elif type(part) is int and isinstance(value, list) and 0 <= part < len(value):
            value = value[part]
        else:
            return _MISSING
    return value


def null_empty(before: Any, after: Any, kind: type) -> bool:
    return (before is None and type(after) is kind and after == kind()) or (
        after is None and type(before) is kind and before == kind()
    )


def allowed_path(resource_type: str, path: Path, before: Any, after: Any) -> bool:
    if resource_type == "google_bigquery_table":
        return path in _BIGQUERY or (
            path in _BIGQUERY_EMPTY_MAPS
            and null_empty(value_at(before, path), value_at(after, path), dict)
        )
    if resource_type == "google_project_iam_member":
        return path == ("etag",)
    if resource_type in _IAM_ETAGS:
        return (
            path == ("etag",)
            and type(value_at(before, path)) is str
            and type(value_at(after, path)) is str
        )
    if resource_type == "google_secret_manager_secret":
        return path in _SECRET_EMPTY_MAPS and null_empty(
            value_at(before, path), value_at(after, path), dict
        )
    if resource_type == "google_storage_bucket":
        return (
            path == ("updated",)
            and type(value_at(before, path)) is str
            and type(value_at(after, path)) is str
        )
    if resource_type != "google_cloud_run_v2_job":
        return False
    if path in _EMPTY_MAPS:
        return null_empty(value_at(before, path), value_at(after, path), dict)
    if path == ("execution_count",) or path[:1] == ("latest_created_execution",):
        # The entire latest execution value is provider-computed runtime metadata.
        return True
    if (
        len(path) == 3
        and path[0] == "terminal_condition"
        and type(path[1]) is int
        and path[2] == "last_transition_time"
    ):
        return True
    if (
        len(path) == 7
        and path[:5] == ("template", 0, "template", 0, "containers")
        and type(path[5]) is int
        and path[6] == "depends_on"
    ):
        return null_empty(value_at(before, path), value_at(after, path), list)
    return False


def has_unknown(value: Any) -> bool:
    if isinstance(value, dict):
        return any(has_unknown(child) for child in value.values())
    if isinstance(value, list):
        return any(has_unknown(child) for child in value)
    return value is not None and value is not False


def review_drift(resources: list[dict[str, Any]]) -> dict[str, int]:
    """Reject all material/malformed drift without printing resource values."""
    if not isinstance(resources, list):
        raise ValueError("EXISTING_INFRASTRUCTURE_DRIFT")
    benign = 0
    for resource in resources:
        if not isinstance(resource, dict) or not isinstance(resource.get("change"), dict):
            raise ValueError("EXISTING_INFRASTRUCTURE_DRIFT")
        change = resource["change"]
        before, after = change.get("before", _MISSING), change.get("after", _MISSING)
        actions = change.get("actions")
        if (
            actions == ["no-op"]
            and not changed_paths(before, after)
            and not has_unknown(change.get("after_unknown"))
        ):
            continue
        resource_type = resource.get("type")
        if (
            actions != ["update"]
            or not isinstance(resource_type, str)
            or resource_type not in _SUPPORTED
            or resource.get("mode", "managed") != "managed"
            or not isinstance(before, dict)
            or not isinstance(after, dict)
            or has_unknown(change.get("after_unknown"))
        ):
            raise ValueError("EXISTING_INFRASTRUCTURE_DRIFT")
        if not all(
            allowed_path(resource_type, p, before, after) for p in changed_paths(before, after)
        ):
            raise ValueError("EXISTING_INFRASTRUCTURE_DRIFT")
        benign += 1
    return {"benign_drift": benign, "material_drift": 0}
