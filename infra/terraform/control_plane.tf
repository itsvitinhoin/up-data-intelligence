variable "control_plane_scheduler_paused" {
  description = "Fail-closed recurring automation; enable only after the DEV acceptance cycle."
  type        = bool
  default     = true
}
# Shared control plane. No store-specific resources or pilot-policy dependencies.
variable "control_plane_image" {
  description = "New immutable shared-worker image; null keeps jobs/schedulers unprovisioned until image approval."
  type        = string
  default     = null
  nullable    = true
  validation {
    condition     = var.control_plane_image == null ? true : can(regex("^southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:[a-f0-9]{64}$", var.control_plane_image))
    error_message = "Supply an explicitly approved immutable DEV image."
  }
}
variable "control_plane_max_parallel_stores" {
  type    = number
  default = 2
  validation {
    condition     = var.control_plane_max_parallel_stores >= 1 && var.control_plane_max_parallel_stores <= 10 && floor(var.control_plane_max_parallel_stores) == var.control_plane_max_parallel_stores
    error_message = "Parallel store executions must be an integer in 1..10."
  }
}
variable "control_plane_maximum_bytes_billed" {
  type    = number
  default = 1073741824
  validation {
    condition     = var.control_plane_maximum_bytes_billed > 0 && floor(var.control_plane_maximum_bytes_billed) == var.control_plane_maximum_bytes_billed
    error_message = "Positive integer query ceiling required."
  }
}
variable "control_plane_maximum_total_bytes_billed" {
  type    = number
  default = 137438953472
  validation {
    condition     = var.control_plane_maximum_total_bytes_billed >= var.control_plane_maximum_bytes_billed && floor(var.control_plane_maximum_total_bytes_billed) == var.control_plane_maximum_total_bytes_billed
    error_message = "Explicit bounded execution envelope required."
  }
}
variable "control_plane_meta_secret_version" {
  description = "Global UP Meta secret version reference only; never a token. Null makes Meta fail closed."
  type        = string
  default     = null
  nullable    = true
  validation {
    condition     = var.control_plane_meta_secret_version == null ? true : can(regex("^[1-9][0-9]*$", var.control_plane_meta_secret_version))
    error_message = "Numeric pinned secret version required."
  }
}
variable "control_plane_admin_member" {
  description = "Optional trusted ADMIN_UP server SA; no browser user or project-wide admin grant."
  type        = string
  default     = null
  nullable    = true
  validation {
    condition     = var.control_plane_admin_member == null ? true : can(regex("^serviceAccount:[a-zA-Z0-9_-]+@[a-zA-Z0-9.-]+\\.iam\\.gserviceaccount\\.com$", var.control_plane_admin_member))
    error_message = "Trusted server service account required."
  }
}
locals {
  control_plane_pipelines  = toset(["upzero", "meta", "analytics", "intelligence"])
  control_plane_identities = setunion(local.control_plane_pipelines, toset(["dispatcher", "scheduler"]))
  control_plane_ops_read   = toset(["store_runtime_config", "sync_runs", "sync_checkpoints", "source_connections", "meta_account_bindings"])
  control_plane_reads = {
    dispatcher   = setunion(local.control_plane_ops_read, toset(["analytics_publications"]))
    upzero       = toset(["store_runtime_config", "source_connections"])
    meta         = toset(["store_runtime_config", "source_connections", "meta_account_bindings"])
    analytics    = setunion(local.control_plane_ops_read, local.analytics_core_read_tables)
    intelligence = setunion(local.control_plane_ops_read, toset(["customers", "orders", "order_items", "analytics_events", "identity_links", "meta_live_campaigns", "meta_live_insights_daily", "analytics_publications"]))
  }
  control_plane_writes = {
    # This is a constant table inventory, never a store inventory.
    upzero       = setunion(toset(["store_runtime_config"]), toset([for name, spec in local.tables : name if spec.dataset != "up_analytics" && !contains(["store_runtime_config", "source_connections", "workspace_store_bindings", "onboarding_operations", "installation_plans", "installation_work_units", "installation_extension_plans", "installation_extension_work_units", "integration_operations"], name) && !startswith(name, "meta_")]))
    meta         = setunion(setsubtract(local.change16_meta_tables, toset(["meta_account_bindings"])), toset(["sync_runs", "sync_checkpoints", "quality_results"]))
    analytics    = local.analytics_write_tables
    intelligence = local.change16_intelligence_tables
  }
  control_plane_grants = merge(
    { for item in flatten([for principal, tables in local.control_plane_reads : [for table in tables : { principal = principal, table = table, write = false }]]) : "${item.principal}/read/${item.table}" => item },
    { for item in flatten([for principal, tables in local.control_plane_writes : [for table in tables : { principal = principal, table = table, write = true }]]) : "${item.principal}/write/${item.table}" => item }
  )
  control_plane_base_args = ["--live", "--project", var.project_id, "--confirm-project", var.project_id, "--location", var.region, "--lease-bucket", var.lease_bucket_name,
  "--maximum-bytes-billed", tostring(var.control_plane_maximum_bytes_billed), "--maximum-total-bytes-billed", tostring(var.control_plane_maximum_total_bytes_billed)]
  control_plane_dispatch_args = concat(local.control_plane_base_args, ["--project-number", data.google_project.control_plane.number, "--max-parallel-stores", tostring(var.control_plane_max_parallel_stores)])
  control_plane_schedules     = { upzero = "0 3 * * *", meta = "0 4 * * *", analytics = "0 5 * * *", intelligence = "0 6 * * *" }
}
resource "google_service_account" "control_plane" {
  for_each     = local.control_plane_identities
  account_id   = "up-cp-${each.key}-${var.environment}"
  display_name = "Shared ${each.key} control plane"
  lifecycle {
    precondition {
      condition     = var.project_id == "up-data-intelligence-dev" && var.environment == "dev" && var.region == "southamerica-east1"
      error_message = "Shared runtime is approved only for DEV in the approved region."
    }
  }
  depends_on = [google_project_service.required]
}
resource "google_project_iam_member" "control_plane_query" {
  for_each = local.control_plane_reads
  project  = var.project_id
  role     = "roles/bigquery.jobUser"
  member   = "serviceAccount:${google_service_account.control_plane[each.key].email}"
}
resource "google_project_iam_custom_role" "control_plane_writer" {
  role_id     = "upControlPlaneDataWriter_${var.environment}"
  title       = "Shared table data writer"
  permissions = ["bigquery.tables.get", "bigquery.tables.getData", "bigquery.tables.updateData"]
}
resource "google_bigquery_table_iam_member" "control_plane" {
  for_each   = local.control_plane_grants
  project    = var.project_id
  dataset_id = local.tables[each.value.table].dataset
  table_id   = google_bigquery_table.tables[each.value.table].table_id
  role       = each.value.write ? google_project_iam_custom_role.control_plane_writer.name : "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.control_plane[each.value.principal].email}"
}
resource "google_storage_bucket_iam_member" "control_plane_lease" {
  for_each = local.control_plane_reads
  bucket   = google_storage_bucket.leases.name
  role     = google_project_iam_custom_role.lease_writer.name
  member   = "serviceAccount:${google_service_account.control_plane[each.key].email}"
}
# New UP Zero sources can use this reviewed naming namespace without per-store Terraform.
# The registry/source_connections remain trusted-admin-owned, not browser input.
resource "google_project_iam_member" "control_plane_upzero_secret" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.control_plane["upzero"].email}"
  condition {
    title       = "UPZeroServerSecretsOnly"
    expression  = "resource.name.startsWith('projects/${data.google_project.control_plane.number}/secrets/up-intelligence-upzero-')"
    description = "Only UP Zero secrets in this project and reviewed naming namespace."
  }
}
resource "google_secret_manager_secret_iam_member" "control_plane_meta_secret" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.change16_meta.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.control_plane["meta"].email}"
}
resource "google_bigquery_table_iam_member" "control_plane_admin" {
  count      = var.control_plane_admin_member == null ? 0 : 1
  project    = var.project_id
  dataset_id = "up_ops"
  table_id   = google_bigquery_table.tables["store_runtime_config"].table_id
  role       = google_project_iam_custom_role.control_plane_writer.name
  member     = var.control_plane_admin_member
}
resource "google_project_iam_member" "control_plane_admin_query" {
  count   = var.control_plane_admin_member == null ? 0 : 1
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = var.control_plane_admin_member
}
resource "google_bigquery_table_iam_member" "control_plane_admin_read" {
  for_each   = var.control_plane_admin_member == null ? toset([]) : toset(["source_connections", "meta_account_bindings"])
  project    = var.project_id
  dataset_id = local.tables[each.key].dataset
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = "roles/bigquery.dataViewer"
  member     = var.control_plane_admin_member
}
resource "google_storage_bucket_iam_member" "control_plane_admin_lease" {
  count  = var.control_plane_admin_member == null ? 0 : 1
  bucket = google_storage_bucket.leases.name
  role   = google_project_iam_custom_role.lease_writer.name
  member = var.control_plane_admin_member
}
resource "google_cloud_run_v2_job" "control_plane_worker" {
  for_each            = var.control_plane_image == null ? toset([]) : local.control_plane_pipelines
  name                = "up-${each.key}-worker"
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.control_plane[each.key].email
      max_retries     = 0
      timeout         = "3600s"
      containers {
        name    = "worker"
        image   = var.control_plane_image
        command = ["python", "-m", "src.control_plane.worker"]
        # Incomplete by design: store/revision/window MUST arrive via dispatcher overrides.
        args = concat(local.control_plane_base_args, ["--pipeline", each.key])
        dynamic "env" {
          for_each = each.key == "meta" && var.control_plane_meta_secret_version != null ? [1] : []
          content {
            name  = "UP_META_SECRET_REFERENCE"
            value = "projects/${var.project_id}/secrets/${var.change16_meta_secret_id}/versions/${var.control_plane_meta_secret_version}"
          }
        }
        dynamic "env" {
          for_each = var.dashboard_completion_enabled ? [1] : []
          content {
            name  = "UP_INSTALLATION_EXTENSIONS_ENABLED"
            value = "1"
          }
        }
        resources { limits = { cpu = "2", memory = "4Gi" } }
      }
    }
  }
  depends_on = [google_bigquery_table_iam_member.control_plane, google_storage_bucket_iam_member.control_plane_lease, google_project_iam_member.control_plane_query, google_project_iam_member.control_plane_upzero_secret, google_secret_manager_secret_iam_member.control_plane_meta_secret]
}
resource "google_cloud_run_v2_job" "control_plane_dispatcher" {
  count               = var.control_plane_image == null ? 0 : 1
  name                = "up-store-dispatcher"
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.control_plane["dispatcher"].email
      max_retries     = 0
      timeout         = "86400s"
      containers {
        name    = "dispatcher"
        image   = var.control_plane_image
        command = ["python", "-m", "src.control_plane.dispatcher_cli"]
        args    = local.control_plane_dispatch_args
        dynamic "env" {
          for_each = var.dashboard_completion_enabled ? [1] : []
          content {
            name  = "UP_INSTALLATION_EXTENSIONS_ENABLED"
            value = "1"
          }
        }
        resources { limits = { cpu = "1", memory = "512Mi" } }
      }
    }
  }
  depends_on = [google_cloud_run_v2_job.control_plane_worker, google_bigquery_table_iam_member.control_plane, google_storage_bucket_iam_member.control_plane_lease]
}
# run.invoker is insufficient for argument overrides. Grant only the specific operation.
resource "google_project_iam_custom_role" "control_plane_run" {
  role_id     = "upControlPlaneRun_${var.environment}"
  title       = "Run shared jobs with overrides"
  permissions = ["run.jobs.run", "run.jobs.runWithOverrides", "run.jobs.get", "run.executions.get"]
}
resource "google_project_iam_custom_role" "control_plane_poll" {
  role_id     = "upControlPlanePoll_${var.environment}"
  title       = "Read shared launch operations"
  permissions = ["run.operations.get"]
}
resource "google_project_iam_member" "control_plane_poll" {
  project = var.project_id
  role    = google_project_iam_custom_role.control_plane_poll.name
  member  = "serviceAccount:${google_service_account.control_plane["dispatcher"].email}"
}
resource "google_cloud_run_v2_job_iam_member" "control_plane_run" {
  for_each = google_cloud_run_v2_job.control_plane_worker
  name     = each.value.name
  location = var.region
  role     = google_project_iam_custom_role.control_plane_run.name
  member   = "serviceAccount:${google_service_account.control_plane["dispatcher"].email}"
}
resource "google_cloud_run_v2_job_iam_member" "control_plane_schedule" {
  count    = var.control_plane_image == null ? 0 : 1
  name     = google_cloud_run_v2_job.control_plane_dispatcher[0].name
  location = var.region
  role     = google_project_iam_custom_role.control_plane_run.name
  member   = "serviceAccount:${google_service_account.control_plane["scheduler"].email}"
}
resource "google_cloud_scheduler_job" "control_plane" {
  for_each  = var.control_plane_image == null ? {} : local.control_plane_schedules
  name      = "up-${each.key}-dispatch"
  region    = var.region
  schedule  = each.value
  time_zone = "Etc/UTC"
  paused    = var.control_plane_scheduler_paused
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.control_plane_dispatcher[0].name}:run"
    body        = base64encode(jsonencode({ overrides = { containerOverrides = [{ name = "dispatcher", args = concat(local.control_plane_dispatch_args, ["--pipeline", each.key, "--window-mode", "previous-closed-day"]) }], taskCount = 1 } }))
    headers     = { "Content-Type" = "application/json" }
    oauth_token {
      service_account_email = google_service_account.control_plane["scheduler"].email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.control_plane_schedule]
}

data "google_project" "control_plane" {
  project_id = var.project_id
}
