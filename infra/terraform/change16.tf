# CHANGE #16: new scoped identities only. Existing identities/IAM remain unchanged.
variable "change16_meta_secret_id" {
  type    = string
  default = "up-intelligence-meta-global-token"
}
variable "change16_runtime" {
  description = "Enable only after account approval and a new immutable image; no automatic scheduler."
  type = object({
    image          = string
    account_id     = string
    api_version    = string
    secret_version = string
  })
  default  = null
  nullable = true
  validation {
    condition = var.change16_runtime == null ? true : (
      can(regex("@sha256:[a-f0-9]{64}$", var.change16_runtime.image)) &&
      can(regex("^[0-9]+$", var.change16_runtime.account_id)) &&
      can(regex("^v[0-9]+\\.0$", var.change16_runtime.api_version)) &&
      can(regex("^[1-9][0-9]*$", var.change16_runtime.secret_version))
    )
    error_message = "Explicit immutable image, account and API version required."
  }
}
locals {
  change16_meta_tables         = toset([for name, spec in local.tables : name if startswith(name, "meta_live_") || startswith(name, "meta_raw_") || name == "meta_account_bindings"])
  change16_intelligence_tables = toset([for name, spec in local.tables : name if spec.dataset == "up_analytics" && !contains(tolist(local.analytics_write_tables), name)])
  change16_read_tables         = setunion(toset(["customers", "orders", "order_items", "analytics_events", "identity_links"]), local.change16_meta_tables, local.analytics_write_tables)
}
resource "google_service_account" "change16" {
  for_each     = toset(["meta", "intelligence"])
  account_id   = "up-${each.key}-${var.environment}"
  display_name = "CHANGE 16 DEV ${each.key}"
  lifecycle {
    precondition {
      condition     = var.project_id == "up-data-intelligence-dev" && var.environment == "dev"
      error_message = "CHANGE 16 pilot config is DEV only."
    }
  }
}
resource "google_project_iam_member" "change16_jobs" {
  for_each = google_service_account.change16
  project  = var.project_id
  role     = "roles/bigquery.jobUser"
  member   = "serviceAccount:${each.value.email}"
}
resource "google_bigquery_table_iam_member" "change16_meta_write" {
  for_each   = setunion(local.change16_meta_tables, toset(["sync_runs", "sync_checkpoints", "quality_results"]))
  project    = var.project_id
  dataset_id = local.tables[each.key].dataset
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = google_project_iam_custom_role.data_writer.name
  member     = "serviceAccount:${google_service_account.change16["meta"].email}"
}
resource "google_bigquery_table_iam_member" "change16_read" {
  for_each   = setunion(local.change16_read_tables, toset(["sync_runs", "sync_checkpoints"]))
  project    = var.project_id
  dataset_id = local.tables[each.key].dataset
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.change16["intelligence"].email}"
}
resource "google_bigquery_table_iam_member" "change16_write" {
  for_each   = local.change16_intelligence_tables
  project    = var.project_id
  dataset_id = "up_analytics"
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = google_project_iam_custom_role.data_writer.name
  member     = "serviceAccount:${google_service_account.change16["intelligence"].email}"
}
resource "google_secret_manager_secret" "change16_meta" {
  project             = var.project_id
  secret_id           = var.change16_meta_secret_id
  labels              = { application = "up-data-intelligence", environment = var.environment }
  deletion_protection = true
  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.required]
}
resource "google_secret_manager_secret_iam_member" "change16_meta" {
  project   = google_secret_manager_secret.change16_meta.project
  secret_id = google_secret_manager_secret.change16_meta.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.change16["meta"].email}"
}
resource "google_storage_bucket_iam_member" "change16_lease" {
  for_each = google_service_account.change16
  bucket   = google_storage_bucket.leases.name
  role     = google_project_iam_custom_role.lease_writer.name
  member   = "serviceAccount:${each.value.email}"
}
resource "google_cloud_run_v2_job" "change16" {
  for_each            = var.change16_runtime == null ? toset([]) : toset(["meta", "intelligence"])
  name                = "up-${each.key}-manual-dev"
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.change16[each.key].email
      max_retries     = 0
      timeout         = "3600s"
      containers {
        image   = var.change16_runtime.image
        command = ["python", "-m", "src.intelligence.live.cli"]
        # Manual argument overrides required for controlled snapshot/calculated_at on materialize.
        args = [
          each.key == "meta" ? "meta-sync" : "materialize",
          "--live", "--project", var.project_id, "--confirm-project", var.project_id,
          "--location", var.region, "--policy", "config/analytics/mx-fashion.dev.json",
          "--store-id", var.pilot.store_id, "--confirm-store", var.pilot.store_id,
          "--account-id", var.change16_runtime.account_id, "--confirm-account-id", var.change16_runtime.account_id,
          "--api-version", var.change16_runtime.api_version,
          "--secret-reference", "projects/${var.project_id}/secrets/${var.change16_meta_secret_id}/versions/${var.change16_runtime.secret_version}",
          "--lease-bucket", var.lease_bucket_name
        ]
        resources { limits = { cpu = "2", memory = "4Gi" } }
      }
    }
  }
  depends_on = [google_bigquery_table_iam_member.change16_meta_write, google_bigquery_table_iam_member.change16_read, google_bigquery_table_iam_member.change16_write, google_secret_manager_secret_iam_member.change16_meta, google_storage_bucket_iam_member.change16_lease]
}
# No Scheduler is created. All existing Schedulers remain paused.

# Explicit server principal only; no browser identity receives BigQuery access.
variable "change16_dashboard_reader_member" {
  type     = string
  default  = null
  nullable = true
  validation {
    condition     = var.change16_dashboard_reader_member == null ? true : can(regex("^serviceAccount:[a-zA-Z0-9_-]+@[a-zA-Z0-9.-]+\\.iam\\.gserviceaccount\\.com$", var.change16_dashboard_reader_member))
    error_message = "Explicit server service account required."
  }
}
resource "google_bigquery_table_iam_member" "change16_dashboard_read" {
  for_each   = var.change16_dashboard_reader_member == null ? toset([]) : local.change16_intelligence_tables
  project    = var.project_id
  dataset_id = "up_analytics"
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = "roles/bigquery.dataViewer"
  member     = var.change16_dashboard_reader_member
}
