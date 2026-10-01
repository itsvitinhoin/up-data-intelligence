"""Synthetic saved plans only: exact drift paths and unchanged additive guards."""

from copy import deepcopy

import pytest

from scripts import change16_plan_guard, control_plane_plan_guard
from scripts.terraform_drift_guard import changed_paths

BQ = "google_bigquery_table"
RUN = "google_cloud_run_v2_job"
IAM = "google_project_iam_member"
CONTAINER = ("template", 0, "template", 0, "containers", 0)


@pytest.fixture(
    params=[change16_plan_guard, control_plane_plan_guard], ids=["change16", "control-plane"]
)
def guard(request):
    return request.param


def put(record, path, value):
    current = record
    for i, part in enumerate(path):
        if isinstance(current, list):
            while len(current) <= part:
                current.append({})
        if i == len(path) - 1:
            current[part] = value
        else:
            if isinstance(current, dict) and part not in current:
                current[part] = [] if isinstance(path[i + 1], int) else {}
            current = current[part]


def drift(kind, path, old, new):
    before = {"name": "synthetic-resource"}
    put(before, path, old)
    after = deepcopy(before)
    put(after, path, new)
    return {"type": kind, "change": {"actions": ["update"], "before": before, "after": after}}


BENIGN = [
    (BQ, ("etag",), "old", "new"),
    (BQ, ("num_rows",), 0, 100),
    (BQ, ("num_bytes",), 0, 1000),
    (BQ, ("last_modified_time",), 1, 2),
    (RUN, ("execution_count",), 1, 2),
    (
        RUN,
        ("latest_created_execution",),
        None,
        [{"name": "synthetic-execution", "completion_time": "later"}],
    ),
    (RUN, ("latest_created_execution",), [{"name": "old"}], [{"name": "new"}, {"name": "later"}]),
    (RUN, ("terminal_condition", 0, "last_transition_time"), "earlier", "later"),
    (RUN, ("terminal_condition", 1, "last_transition_time"), "earlier", "later"),
    (RUN, ("annotations",), None, {}),
    (RUN, ("labels",), None, {}),
    (RUN, ("template", 0, "annotations"), None, {}),
    (RUN, ("template", 0, "labels"), None, {}),
    (RUN, (*CONTAINER, "depends_on"), None, []),
    (RUN, ("template", 0, "template", 0, "containers", 1, "depends_on"), None, []),
    (IAM, ("etag",), "old", "new"),
]


@pytest.mark.parametrize("kind,path,old,new", BENIGN)
def test_explicit_computed_drift_accepted(guard, kind, path, old, new):
    result = guard.check({"resource_drift": [drift(kind, path, old, new)]})
    assert result == {"add": 0, "change": 0, "destroy": 0, "benign_drift": 1, "material_drift": 0}


@pytest.mark.parametrize(
    "path,empty",
    [
        (("annotations",), {}),
        (("labels",), {}),
        (("template", 0, "annotations"), {}),
        (("template", 0, "labels"), {}),
        ((*CONTAINER, "depends_on"), []),
    ],
)
def test_null_empty_normalization_is_symmetric(guard, path, empty):
    assert guard.check({"resource_drift": [drift(RUN, path, empty, None)]})["benign_drift"] == 1


MATERIAL = [
    (BQ, ("schema",), "old", "new"),
    (BQ, ("clustering",), ["store_id"], ["customer_id"]),
    (BQ, ("deletion_protection",), True, False),
    (BQ, ("dataset_id",), "old", "new"),
    (BQ, ("table_id",), "old", "new"),
    (BQ, ("time_partitioning",), [{"field": "old"}], [{"field": "new"}]),
    (BQ, ("require_partition_filter",), True, False),
    (BQ, ("labels",), None, {}),
    (BQ, ("description",), "old", "new"),
    (BQ, ("expiration_time",), 1, 2),
    (BQ, ("encryption_configuration",), None, [{"kms_key_name": "synthetic"}]),
    (BQ, ("friendly_name",), "old", "new"),
    (RUN, (*CONTAINER, "image"), "old@sha256:synthetic", "new@sha256:synthetic"),
    (RUN, (*CONTAINER, "args"), ["old"], ["new"]),
    (RUN, (*CONTAINER, "command"), ["old"], ["new"]),
    (RUN, (*CONTAINER, "env"), [], [{"name": "SYNTHETIC", "value": "example"}]),
    (RUN, ("template", 0, "template", 0, "service_account"), "old", "new"),
    (RUN, (*CONTAINER, "resources", 0, "limits", "cpu"), "1", "2"),
    (RUN, (*CONTAINER, "resources", 0, "limits", "memory"), "1Gi", "2Gi"),
    (RUN, ("template", 0, "template", 0, "timeout"), "10s", "20s"),
    (RUN, ("template", 0, "template", 0, "max_retries"), 0, 1),
    (RUN, ("template", 0, "task_count"), 1, 2),
    (RUN, ("template", 0, "parallelism"), 1, 2),
    (RUN, ("name",), "old", "new"),
    (RUN, ("location",), "old", "new"),
    (RUN, ("deletion_protection",), True, False),
    (RUN, ("template", 0, "template", 0, "vpc_access"), [], [{"network_interfaces": []}]),
    (RUN, ("template", 0, "template", 0, "volumes"), [], [{"name": "synthetic"}]),
    (RUN, ("annotations",), None, {"synthetic": "value"}),
    (RUN, ("labels",), {"synthetic": "old"}, {"synthetic": "new"}),
    (RUN, ("template", 0, "annotations"), {"synthetic": "value"}, None),
    (RUN, ("template", 0, "labels"), None, {"synthetic": "value"}),
    (RUN, (*CONTAINER, "depends_on"), None, ["sidecar"]),
    (RUN, (*CONTAINER, "depends_on"), ["old"], ["new"]),
    (RUN, (*CONTAINER, "depends_on"), ["sidecar"], None),
    (RUN, ("template", 1, "labels"), None, {}),
    (RUN, ("template", 0, "template", 0, "labels"), None, {}),
    (RUN, ("terminal_condition", 0, "state"), "old", "new"),
    (RUN, ("terminal_condition",), None, [{"last_transition_time": "later"}]),
    (IAM, ("project",), "old", "new"),
    (IAM, ("role",), "roles/viewer", "roles/owner"),
    (IAM, ("member",), "synthetic-old", "synthetic-new"),
    (IAM, ("condition",), [], [{"expression": "true"}]),
    (BQ, ("unapproved_future_field",), None, {}),
    (RUN, ("unapproved_future_field",), None, []),
    (IAM, ("unapproved_future_field",), "old", "new"),
]


@pytest.mark.parametrize("kind,path,old,new", MATERIAL)
def test_material_or_unapproved_path_rejected(guard, kind, path, old, new):
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [drift(kind, path, old, new)]})


@pytest.mark.parametrize("kind,path,old,new", MATERIAL)
def test_one_material_path_cannot_hide_among_benign_paths(guard, kind, path, old, new):
    entry = drift(kind, path, old, new)
    entry["change"]["before"]["etag" if kind != RUN else "execution_count"] = "old"
    entry["change"]["after"]["etag" if kind != RUN else "execution_count"] = "new"
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize(
    "actions", [["delete"], ["create"], ["read"], ["delete", "create"], ["create", "delete"]]
)
def test_drift_action_must_be_update(guard, actions):
    entry = drift(BQ, ("etag",), "old", "new")
    entry["change"]["actions"] = actions
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize(
    "actions", [["update"], ["delete"], ["delete", "create"], ["create", "delete"]]
)
def test_planned_changes_remain_forbidden_even_on_computed_fields(guard, actions):
    entry = drift(BQ, ("etag",), "old", "new")
    entry["address"] = 'google_bigquery_table.tables["synthetic"]'
    entry["change"]["actions"] = actions
    with pytest.raises(ValueError, match="NON_ADDITIVE_TERRAFORM_PLAN"):
        guard.check({"resource_changes": [entry]})


@pytest.mark.parametrize(
    "kind", ["google_storage_bucket", "google_project_iam_binding", "future_resource", None]
)
def test_unsupported_drift_resource_rejected(guard, kind):
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [drift(kind, ("etag",), "old", "new")]})


@pytest.mark.parametrize("field", ["before", "after"])
def test_missing_drift_snapshot_rejected(guard, field):
    entry = drift(BQ, ("etag",), "old", "new")
    del entry["change"][field]
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize("path,empty", [(("labels",), {}), ((*CONTAINER, "depends_on"), [])])
def test_missing_is_not_null_normalization(guard, path, empty):
    entry = drift(RUN, path, None, empty)
    target = entry["change"]["before"]
    for part in path[:-1]:
        target = target[part]
    del target[path[-1]]
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize("unknown", [True, {"schema": True}, {"latest_created_execution": [True]}])
def test_unknown_after_cannot_mask_changes(guard, unknown):
    entry = drift(BQ, ("etag",), "old", "new")
    entry["change"]["after_unknown"] = unknown
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})


def test_new_container_not_hidden_by_depends_on_normalization(guard):
    entry = drift(RUN, (*CONTAINER, "depends_on"), None, [])
    entry["change"]["after"]["template"][0]["template"][0]["containers"].append({"depends_on": []})
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})


def test_noop_and_read_planned_actions_still_allowed(guard):
    assert (
        guard.check(
            {
                "resource_changes": [
                    {"change": {"actions": ["no-op"]}},
                    {"change": {"actions": ["read"]}},
                ]
            }
        )["add"]
        == 0
    )
    entry = drift(BQ, ("etag",), "same", "same")
    entry["change"]["actions"] = ["no-op"]
    assert guard.check({"resource_drift": [entry]})["benign_drift"] == 0
    entry["change"]["after"]["etag"] = "changed"
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})


def test_fourteen_synthetic_operational_entries_counted_per_resource(guard):
    entries = [drift(BQ, ("etag",), "old", "new") for _ in range(12)]
    cloud = drift(RUN, ("annotations",), None, {})
    cloud["change"]["before"].update(labels=None, execution_count=1, latest_created_execution=None)
    cloud["change"]["after"].update(
        labels={}, execution_count=2, latest_created_execution=[{"name": "synthetic"}]
    )
    for path, old, new in [
        (("template", 0, "annotations"), None, {}),
        (("template", 0, "labels"), None, {}),
        ((*CONTAINER, "depends_on"), None, []),
        (("terminal_condition", 0, "last_transition_time"), "earlier", "later"),
    ]:
        put(cloud["change"]["before"], path, old)
        put(cloud["change"]["after"], path, new)
    entries.extend([cloud, drift(IAM, ("etag",), "old", "new")])
    resource = "change16" if guard is change16_plan_guard else "control_plane"
    creates = [
        {
            "address": f'google_service_account.{resource}["synthetic-{i}"]',
            "type": "google_service_account",
            "change": {"actions": ["create"], "after": {}},
        }
        for i in range(2)
    ]
    assert guard.check({"resource_changes": creates, "resource_drift": entries}) == {
        "add": 2,
        "change": 0,
        "destroy": 0,
        "benign_drift": 14,
        "material_drift": 0,
    }
    entries.append(drift(BQ, ("schema",), "old", "new"))
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": entries})


def test_recursive_diff_is_deterministic_and_distinguishes_absence():
    before = {"z": None, "a": [{"x": 1, "y": []}], "removed": None}
    after = {"a": [{"x": 2, "y": None}, {}], "z": {}, "added": None}
    assert changed_paths(before, after) == [
        ("a", 0, "x"),
        ("a", 0, "y"),
        ("a", 1),
        ("added",),
        ("removed",),
        ("z",),
    ]
    assert changed_paths({"a": True}, {"a": 1}) == [("a",)]


@pytest.mark.parametrize(
    "resources",
    [
        None,
        {},
        [None],
        [{}],
        [{"change": None}],
        [{"type": [], "change": {"actions": ["update"], "before": {}, "after": {}}}],
    ],
)
def test_malformed_drift_rejected_with_controlled_error(guard, resources):
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": resources})


def test_data_resource_cannot_use_managed_operational_allowlist(guard):
    entry = drift(BQ, ("etag",), "old", "new")
    entry["mode"] = "data"
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})


def test_noop_cannot_hide_boolean_integer_type_difference(guard):
    entry = drift(BQ, ("deletion_protection",), True, 1)
    entry["change"]["actions"] = ["no-op"]
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        guard.check({"resource_drift": [entry]})
