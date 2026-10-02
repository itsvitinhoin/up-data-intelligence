"""Synthetic saved plans only: exact drift paths and unchanged additive guards."""

from copy import deepcopy

import pytest

from scripts import change16_plan_guard, control_plane_plan_guard
from scripts.terraform_drift_guard import _SUPPORTED, changed_paths

BQ = "google_bigquery_table"
RUN = "google_cloud_run_v2_job"
IAM = "google_project_iam_member"
BQ_IAM = "google_bigquery_table_iam_member"
SECRET = "google_secret_manager_secret"
SECRET_IAM = "google_secret_manager_secret_iam_member"
BUCKET = "google_storage_bucket"
BUCKET_IAM = "google_storage_bucket_iam_member"
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
    (BQ, ("labels",), None, {"env": "x"}),
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
    "kind",
    ["google_storage_bucket_iam_binding", "google_project_iam_binding", "future_resource", None],
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


EMPTY_MAP_DRIFT = [
    (BQ, ("labels",)),
    (BQ, ("resource_tags",)),
    (SECRET, ("annotations",)),
    (SECRET, ("version_aliases",)),
]
STRING_METADATA_DRIFT = [
    (BQ_IAM, ("etag",)),
    (SECRET_IAM, ("etag",)),
    (BUCKET, ("updated",)),
    (BUCKET_IAM, ("etag",)),
]
NEW_BENIGN = [(kind, path, None, {}) for kind, path in EMPTY_MAP_DRIFT] + [
    (kind, path, "earlier", "later") for kind, path in STRING_METADATA_DRIFT
]


def test_supported_types_are_exactly_the_eight_approved_types():
    assert _SUPPORTED == {BQ, RUN, IAM, BQ_IAM, SECRET, SECRET_IAM, BUCKET, BUCKET_IAM}


@pytest.mark.parametrize("kind,path,old,new", NEW_BENIGN)
def test_provider_metadata_normalization_accepted(guard, kind, path, old, new):
    assert guard.check({"resource_drift": [drift(kind, path, old, new)]}) == {
        "add": 0,
        "change": 0,
        "destroy": 0,
        "benign_drift": 1,
        "material_drift": 0,
    }


@pytest.mark.parametrize("kind,path", EMPTY_MAP_DRIFT)
def test_new_empty_map_normalization_is_symmetric(guard, kind, path):
    assert guard.check({"resource_drift": [drift(kind, path, {}, None)]})["benign_drift"] == 1


@pytest.mark.parametrize("kind,path", EMPTY_MAP_DRIFT)
@pytest.mark.parametrize(
    "old,new",
    [
        ({"env": "x"}, {}),
        ({}, {"env": "x"}),
        (None, {"env": "x"}),
        ({"env": "x"}, None),
        ({"env": "x"}, {"env": "y"}),
        (None, []),
    ],
)
def test_new_maps_reject_real_content_and_wrong_shape(guard, kind, path, old, new):
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [drift(kind, path, old, new)]})


@pytest.mark.parametrize("kind,path", EMPTY_MAP_DRIFT + STRING_METADATA_DRIFT)
@pytest.mark.parametrize("missing_snapshot", ["before", "after"])
def test_new_metadata_requires_explicit_path_in_both_snapshots(guard, kind, path, missing_snapshot):
    old, new = (None, {}) if (kind, path) in EMPTY_MAP_DRIFT else ("earlier", "later")
    entry = drift(kind, path, old, new)
    del entry["change"][missing_snapshot][path[0]]
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize("kind,path", STRING_METADATA_DRIFT)
@pytest.mark.parametrize("invalid", [None, 1, True, [], {}])
@pytest.mark.parametrize("side", ["before", "after"])
def test_new_computed_metadata_requires_strings_on_both_sides(guard, kind, path, invalid, side):
    entry = drift(kind, path, "earlier", "later")
    entry["change"][side][path[0]] = invalid
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize("kind,path,old,new", NEW_BENIGN)
def test_new_metadata_allowlist_is_top_level_only(guard, kind, path, old, new):
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [drift(kind, ("nested", *path), old, new)]})


NEW_MATERIAL = [
    (BQ_IAM, ("member",), "synthetic-old", "synthetic-new"),
    (BQ_IAM, ("role",), "roles/viewer", "roles/owner"),
    (BQ_IAM, ("condition",), [], [{"expression": "true"}]),
    (BQ_IAM, ("dataset_id",), "old", "new"),
    (BQ_IAM, ("table_id",), "old", "new"),
    (SECRET, ("replication",), [], [{"auto": [{}]}]),
    (SECRET, ("labels",), None, {}),
    (SECRET, ("secret_id",), "old", "new"),
    (SECRET, ("deletion_protection",), True, False),
    (SECRET_IAM, ("member",), "synthetic-old", "synthetic-new"),
    (SECRET_IAM, ("role",), "roles/viewer", "roles/owner"),
    (SECRET_IAM, ("condition",), [], [{"expression": "true"}]),
    (SECRET_IAM, ("secret_id",), "old", "new"),
    (BUCKET, ("location",), "old", "new"),
    (BUCKET, ("retention_policy",), [{"retention_period": 100}], [{"retention_period": 200}]),
    (BUCKET, ("uniform_bucket_level_access",), True, False),
    (BUCKET, ("force_destroy",), False, True),
    (BUCKET, ("labels",), None, {}),
    (BUCKET, ("versioning",), [{"enabled": True}], [{"enabled": False}]),
    (BUCKET, ("lifecycle_rule",), [], [{"action": [{"type": "Delete"}]}]),
    (BUCKET, ("public_access_prevention",), "enforced", "inherited"),
    (BUCKET, ("etag",), "old", "new"),
    (BUCKET_IAM, ("member",), "synthetic-old", "synthetic-new"),
    (BUCKET_IAM, ("role",), "roles/viewer", "roles/owner"),
    (BUCKET_IAM, ("condition",), [], [{"expression": "true"}]),
    (BUCKET_IAM, ("bucket",), "old", "new"),
]


@pytest.mark.parametrize("kind,path,old,new", NEW_MATERIAL)
@pytest.mark.parametrize("include_benign", [False, True])
def test_new_resource_types_reject_material_changes_even_with_metadata(
    guard, kind, path, old, new, include_benign
):
    entry = drift(kind, path, old, new)
    if include_benign:
        benign_path = "annotations" if kind == SECRET else "updated" if kind == BUCKET else "etag"
        entry["change"]["before"][benign_path] = None if kind == SECRET else "earlier"
        entry["change"]["after"][benign_path] = {} if kind == SECRET else "later"
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize("kind", sorted(_SUPPORTED))
@pytest.mark.parametrize("unknown", [True, {"nested": [False, {"leaf": True}]}])
def test_all_supported_types_still_reject_unknown_values(guard, kind, unknown):
    case = next(case for case in NEW_BENIGN + BENIGN if case[0] == kind)
    entry = drift(*case)
    entry["change"]["after_unknown"] = unknown
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [entry]})
    entry["change"]["after"] = deepcopy(entry["change"]["before"])
    entry["change"]["actions"] = ["no-op"]
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize("kind,path,old,new", NEW_BENIGN)
@pytest.mark.parametrize(
    "actions",
    [["create"], ["delete"], ["delete", "create"], ["create", "delete"], ["read"], ["no-op"]],
)
def test_new_metadata_drift_does_not_authorize_other_actions(guard, kind, path, old, new, actions):
    entry = drift(kind, path, old, new)
    entry["change"]["actions"] = actions
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [entry]})


@pytest.mark.parametrize("kind,path,old,new", NEW_BENIGN)
def test_new_resource_noop_without_differences_remains_accepted(guard, kind, path, old, new):
    entry = drift(kind, path, old, old)
    entry["change"]["actions"] = ["no-op"]
    entry["change"]["after_unknown"] = {"nested": [False, {"leaf": None}]}
    assert guard.check({"resource_drift": [entry]})["benign_drift"] == 0
    entry["change"]["after"][path[0]] = new
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": [entry]})


@pytest.fixture
def provider_840_drift():
    """143 synthetic resources; paired empty maps belong to the same resource."""
    tables = [drift(BQ, ("labels",), None, {}) for _ in range(30)]
    for table in tables:
        table["change"]["before"]["resource_tags"] = None
        table["change"]["after"]["resource_tags"] = {}
    secret = drift(SECRET, ("annotations",), None, {})
    secret["change"]["before"]["version_aliases"] = None
    secret["change"]["after"]["version_aliases"] = {}
    return (
        tables
        + [drift(BQ_IAM, ("etag",), "old", "new") for _ in range(106)]
        + [secret, drift(SECRET_IAM, ("etag",), "old", "new")]
        + [drift(BUCKET, ("updated",), "2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z")]
        + [drift(BUCKET_IAM, ("etag",), "old", "new") for _ in range(4)]
    )


def test_provider_840_workload_shared_by_both_plan_guards(guard, provider_840_drift):
    assert guard.check({"resource_drift": provider_840_drift}) == {
        "add": 0,
        "change": 0,
        "destroy": 0,
        "benign_drift": 143,
        "material_drift": 0,
    }
    provider_840_drift[-1]["change"]["after"]["member"] = "synthetic-new"
    with pytest.raises(ValueError, match="^EXISTING_INFRASTRUCTURE_DRIFT$"):
        guard.check({"resource_drift": provider_840_drift})


@pytest.fixture
def control_plane_fourteen_creations():
    resources = []
    for kind, name, pipelines in [
        (RUN, "control_plane_worker", ["upzero", "meta", "analytics", "intelligence"]),
        (RUN, "control_plane_dispatcher", [None]),
        (
            "google_cloud_run_v2_job_iam_member",
            "control_plane_run",
            ["upzero", "meta", "analytics", "intelligence"],
        ),
        ("google_cloud_run_v2_job_iam_member", "control_plane_schedule", [None]),
        (
            "google_cloud_scheduler_job",
            "control_plane",
            ["upzero", "meta", "analytics", "intelligence"],
        ),
    ]:
        for pipeline in pipelines:
            address = f"{kind}.{name}" + (f'["{pipeline}"]' if pipeline else "")
            resources.append(
                {
                    "address": address,
                    "type": kind,
                    "change": {
                        "actions": ["create"],
                        "after": {"paused": True} if kind == "google_cloud_scheduler_job" else {},
                    },
                }
            )
    return resources


def test_control_plane_fourteen_additions_with_provider_drift(
    control_plane_fourteen_creations, provider_840_drift
):
    assert control_plane_plan_guard.check(
        {"resource_changes": control_plane_fourteen_creations, "resource_drift": provider_840_drift}
    ) == {"add": 14, "change": 0, "destroy": 0, "benign_drift": 143, "material_drift": 0}


@pytest.mark.parametrize("violation", ["update", "delete", "replace", "unapproved", "scheduler"])
def test_provider_drift_cannot_relax_control_plane_creation_guard(
    control_plane_fourteen_creations, provider_840_drift, violation
):
    changes = control_plane_fourteen_creations
    if violation == "unapproved":
        changes[0]["address"] = "google_cloud_run_v2_job.unapproved"
        error = "UNAPPROVED_RESOURCE"
    elif violation == "scheduler":
        changes[-1]["change"]["after"]["paused"] = False
        error = "SCHEDULER_MUST_REMAIN_PAUSED"
    else:
        changes[0]["change"]["actions"] = (
            ["delete", "create"] if violation == "replace" else [violation]
        )
        error = "NON_ADDITIVE_TERRAFORM_PLAN"
    with pytest.raises(ValueError, match=f"^{error}$"):
        control_plane_plan_guard.check(
            {"resource_changes": changes, "resource_drift": provider_840_drift}
        )
