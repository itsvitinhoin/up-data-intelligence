# Detector only: no secrets, source API credentials, leases or business-table writes.
variable "data_health_image" {
  type     = string
  default  = null
  nullable = true
  validation {
    condition     = var.data_health_image == null ? true : can(regex("^southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:[a-f0-9]{64}$", var.data_health_image))
    error_message = "The health detector requires an approved immutable DEV image."
  }
}
variable "data_health_scheduler_paused" {
  type    = bool
  default = true
}
locals {
  data_health_reads = var.data_health_image == null ? toset([]) : toset([
    "store_runtime_config", "sync_checkpoints", "sync_runs", "source_connections",
    "meta_account_bindings", "analytics_publications", "analytics_intelligence_publications",
    "analytics_store_daily"
  ])
  data_health_args = [
    "--live", "--project", var.project_id, "--confirm-project", var.project_id,
    "--location", var.region, "--all-stores", "--max-stores", "10",
    "--maximum-bytes-billed", "1073741824",
    "--maximum-total-bytes-billed", "137438953472"
  ]
}
resource "google_service_account" "data_health" {
  count        = var.data_health_image == null ? 0 : 1
  account_id   = "up-data-health-${var.environment}"
  display_name = "Durable data health detector; no source credentials"
  lifecycle {
    precondition {
      condition     = var.project_id == "up-data-intelligence-dev" && var.environment == "dev" && var.region == "southamerica-east1"
      error_message = "Health deployment is approved only for DEV."
    }
  }
}
resource "google_project_iam_member" "data_health_query" {
  count   = var.data_health_image == null ? 0 : 1
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.data_health[0].email}"
}
resource "google_bigquery_table_iam_member" "data_health_read" {
  for_each   = local.data_health_reads
  project    = var.project_id
  dataset_id = local.tables[each.key].dataset
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.data_health[0].email}"
}
resource "google_bigquery_table_iam_member" "data_health_results" {
  count      = var.data_health_image == null ? 0 : 1
  project    = var.project_id
  dataset_id = "up_ops"
  table_id   = google_bigquery_table.tables["quality_results"].table_id
  role       = google_project_iam_custom_role.control_plane_writer.name
  member     = "serviceAccount:${google_service_account.data_health[0].email}"
}
resource "google_cloud_run_v2_job" "data_health" {
  count               = var.data_health_image == null ? 0 : 1
  name                = "up-data-health"
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.data_health[0].email
      max_retries     = 0
      timeout         = "3600s"
      containers {
        name    = "health"
        image   = var.data_health_image
        command = ["python", "-m", "src.quality.data_health_cli"]
        args    = local.data_health_args
        resources { limits = { cpu = "1", memory = "512Mi" } }
      }
    }
  }
  depends_on = [google_bigquery_table_iam_member.data_health_read, google_bigquery_table_iam_member.data_health_results, google_project_iam_member.data_health_query]
}
resource "google_cloud_run_v2_job_iam_member" "data_health_schedule" {
  count    = var.data_health_image == null ? 0 : 1
  name     = google_cloud_run_v2_job.data_health[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.control_plane["scheduler"].email}"
}
resource "google_cloud_scheduler_job" "data_health" {
  count     = var.data_health_image == null ? 0 : 1
  name      = "up-data-health-dispatch"
  region    = var.region
  schedule  = "0 7 * * *"
  time_zone = "Etc/UTC"
  paused    = var.data_health_scheduler_paused
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.data_health[0].name}:run"
    body        = base64encode(jsonencode({}))
    headers     = { "Content-Type" = "application/json" }
    oauth_token {
      service_account_email = google_service_account.control_plane["scheduler"].email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.data_health_schedule]
}
