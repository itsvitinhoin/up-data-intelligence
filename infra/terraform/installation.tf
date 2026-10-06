variable "installation_scheduler_paused" {
  description = "New installation automation must be deployed paused before acceptance."
  type        = bool
  default     = true
}
# Separate bounded installation runtime; automation remains fail-closed by default.
variable "installation_image" {
  description = "Future approved immutable installation image; null leaves all four jobs absent."
  type        = string
  default     = null
  nullable    = true
  validation {
    condition     = var.installation_image == null ? true : can(regex("^southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:[a-f0-9]{64}$", var.installation_image))
    error_message = "Approved immutable DEV digest required."
  }
}
variable "installation_page_budget" {
  type    = number
  default = 20
  validation {
    condition     = var.installation_page_budget >= 1 && var.installation_page_budget <= 20 && floor(var.installation_page_budget) == var.installation_page_budget
    error_message = "Conservative page budget: integer in 1..20."
  }
}
variable "installation_soft_time_budget_seconds" {
  type    = number
  default = 600
  validation {
    condition     = var.installation_soft_time_budget_seconds > 0 && var.installation_soft_time_budget_seconds <= 600
    error_message = "Cooperative slice ceiling must be within 600 seconds."
  }
}
locals {
  installation_workers = toset(["upzero", "meta", "analytics"])
  installation_read = {
    orchestrator = toset(["onboarding_operations", "meta_account_bindings", "store_runtime_config", "source_connections", "sync_runs", "sync_checkpoints", "analytics_publications", "analytics_store_daily", "analytics_funnel_daily", "installation_plans", "installation_work_units"])
    upzero       = toset(["installation_plans", "installation_work_units"])
    meta         = toset(["installation_plans", "installation_work_units"])
    analytics    = toset(["installation_plans", "installation_work_units"])
  }
  installation_write = {
    orchestrator = toset(["installation_plans", "installation_work_units", "store_runtime_config", "onboarding_operations"])
    upzero       = toset(["installation_work_units", "source_connections"])
    meta         = toset(["installation_work_units", "source_connections"])
    analytics    = toset(["installation_work_units"])
  }
  installation_grants = merge(
    { for item in flatten([for principal, tables in local.installation_read : [for table in tables : { principal = principal, table = table, write = false }]]) : "${item.principal}/read/${item.table}" => item },
    { for item in flatten([for principal, tables in local.installation_write : [for table in tables : { principal = principal, table = table, write = true }]]) : "${item.principal}/write/${item.table}" => item }
  )
  installation_args = concat(local.control_plane_base_args, ["--page-budget", tostring(var.installation_page_budget), "--soft-time-budget-seconds", tostring(var.installation_soft_time_budget_seconds), "--max-parallel-stores", tostring(var.control_plane_max_parallel_stores), "--max-stores", "10", "--max-dispatches", "20"])
}
resource "google_service_account" "installation_orchestrator" {
  account_id   = "up-install-orchestrator-${var.environment}"
  display_name = "Installation ledger orchestrator; no credential access"
  lifecycle {
    precondition {
      condition     = var.project_id == "up-data-intelligence-dev" && var.environment == "dev" && var.region == "southamerica-east1"
      error_message = "Installation runtime is approved only for DEV."
    }
  }
  depends_on = [google_project_service.required]
}
resource "google_project_iam_member" "installation_query" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.installation_orchestrator.email}"
}
resource "google_bigquery_table_iam_member" "installation" {
  for_each   = local.installation_grants
  project    = var.project_id
  dataset_id = local.tables[each.value.table].dataset
  table_id   = google_bigquery_table.tables[each.value.table].table_id
  role       = each.value.write ? google_project_iam_custom_role.control_plane_writer.name : "roles/bigquery.dataViewer"
  member     = "serviceAccount:${each.value.principal == "orchestrator" ? google_service_account.installation_orchestrator.email : google_service_account.control_plane[each.value.principal].email}"
}
resource "google_storage_bucket_iam_member" "installation_lease" {
  bucket = google_storage_bucket.leases.name
  role   = google_project_iam_custom_role.lease_writer.name
  member = "serviceAccount:${google_service_account.installation_orchestrator.email}"
}
resource "google_cloud_run_v2_job" "installation_worker" {
  for_each            = var.installation_image == null ? toset([]) : local.installation_workers
  name                = "up-installation-${each.key}-worker"
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.control_plane[each.key].email
      timeout         = "3600s"
      max_retries     = 0
      containers {
        name    = "worker"
        image   = var.installation_image
        command = ["python", "-m", "src.installation.cli"]
        args    = concat(local.installation_args, ["--worker", "--pipeline", each.key])
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
        dynamic "env" {
          for_each = each.key == "upzero" && var.dashboard_completion_product_images ? [1] : []
          content {
            name  = "UP_INSTALLATION_PRODUCT_IMAGES_ENABLED"
            value = "1"
          }
        }
        resources { limits = { cpu = "2", memory = "4Gi" } }
      }
    }
  }
  depends_on = [google_bigquery_table_iam_member.installation, google_bigquery_table_iam_member.control_plane, google_storage_bucket_iam_member.control_plane_lease]
}
resource "google_cloud_run_v2_job" "installation_orchestrator" {
  count               = var.installation_image == null ? 0 : 1
  name                = "up-installation-orchestrator"
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.installation_orchestrator.email
      timeout         = "3600s"
      max_retries     = 0
      containers {
        name    = "orchestrator"
        image   = var.installation_image
        command = ["python", "-m", "src.installation.cli"]
        # Manual scope intentionally required; do not dispatch all stores accidentally.
        args = concat(local.installation_args, ["--dispatch", "--project-number", data.google_project.control_plane.number])
        dynamic "env" {
          for_each = var.dashboard_completion_product_images ? [1] : []
          content {
            name  = "UP_INSTALLATION_PRODUCT_IMAGES_ENABLED"
            value = "1"
          }
        }
        dynamic "env" {
          for_each = var.dashboard_completion_verified_meta_purchases ? [1] : []
          content {
            name  = "UP_META_VERIFIED_PURCHASES_ENABLED"
            value = "1"
          }
        }
        dynamic "env" {
          for_each = var.dashboard_completion_enabled ? [1] : []
          content {
            name  = "UP_INSTALLATION_EXTENSIONS_ENABLED"
            value = "1"
          }
        }
        dynamic "env" {
          for_each = var.dashboard_completion_enabled && var.dashboard_completion_automatic_enrichment ? [1] : []
          content {
            name  = "UP_INSTALLATION_ENRICHMENT_ENABLED"
            value = "1"
          }
        }
        resources { limits = { cpu = "1", memory = "512Mi" } }
      }
    }
  }
  depends_on = [google_cloud_run_v2_job.installation_worker, google_bigquery_table_iam_member.installation, google_storage_bucket_iam_member.installation_lease]
}
resource "google_cloud_run_v2_job_iam_member" "installation_run" {
  for_each = google_cloud_run_v2_job.installation_worker
  name     = each.value.name
  location = var.region
  role     = google_project_iam_custom_role.control_plane_run.name
  member   = "serviceAccount:${google_service_account.installation_orchestrator.email}"
}
resource "google_project_iam_member" "installation_poll" {
  project = var.project_id
  role    = google_project_iam_custom_role.control_plane_poll.name
  member  = "serviceAccount:${google_service_account.installation_orchestrator.email}"
}
# Read API needs only metadata reads; administrative writes remain table-scoped above.
resource "google_bigquery_table_iam_member" "installation_admin_read" {
  for_each   = var.control_plane_admin_member == null ? toset([]) : toset(["installation_plans", "installation_work_units"])
  project    = var.project_id
  dataset_id = "up_ops"
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = "roles/bigquery.dataViewer"
  member     = var.control_plane_admin_member
}

resource "google_cloud_run_v2_job_iam_member" "installation_schedule" {
  count    = var.installation_image == null ? 0 : 1
  name     = google_cloud_run_v2_job.installation_orchestrator[0].name
  location = var.region
  role     = google_project_iam_custom_role.control_plane_run.name
  member   = "serviceAccount:${google_service_account.control_plane["scheduler"].email}"
}
resource "google_cloud_scheduler_job" "installation" {
  count     = var.installation_image == null ? 0 : 1
  name      = "up-installation-dispatch"
  region    = var.region
  schedule  = "* * * * *"
  time_zone = "Etc/UTC"
  paused    = var.installation_scheduler_paused
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.installation_orchestrator[0].name}:run"
    body        = base64encode(jsonencode({ overrides = { containerOverrides = [{ name = "orchestrator", args = concat(local.installation_args, ["--dispatch", "--all-stores", "--auto-activate", "--project-number", data.google_project.control_plane.number]) }], taskCount = 1 } }))
    headers     = { "Content-Type" = "application/json" }
    oauth_token {
      service_account_email = google_service_account.control_plane["scheduler"].email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.installation_schedule]
}
