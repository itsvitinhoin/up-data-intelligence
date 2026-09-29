# First manual Analytics DEV runtime. No Scheduler and no change to UP Zero Jobs.
variable "analytics_image" {
  type        = string
  description = "New Analytics-compatible image, built/published separately; never reuse DEV.4 implicitly."
  validation {
    condition     = can(regex("^southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:[a-f0-9]{64}$", var.analytics_image))
    error_message = "Supply the approved new immutable DEV image digest."
  }
}
variable "analytics_maximum_bytes_billed" {
  type        = number
  description = "Explicitly approved per-query BigQuery budget; no automatic default."
  validation {
    condition     = var.analytics_maximum_bytes_billed > 0 && floor(var.analytics_maximum_bytes_billed) == var.analytics_maximum_bytes_billed
    error_message = "Supply a positive integer byte budget approved for Analytics."
  }
}
locals {
  analytics_core_read_tables = toset(["customers", "orders", "order_items", "analytics_events"])
  analytics_write_tables = toset([
    "analytics_store_daily", "analytics_customer_metrics", "analytics_customer_purchase_sequence",
    "analytics_cohorts", "analytics_purchase_distribution", "analytics_products_daily",
    "analytics_funnel_daily", "analytics_publications"
  ])
}
resource "google_service_account" "analytics" {
  account_id   = "up-analytics-dev"
  display_name = "Analytics DEV manual materialization"
  lifecycle {
    precondition {
      condition     = var.project_id == "up-data-intelligence-dev" && var.environment == "dev" && var.region == "southamerica-east1"
      error_message = "The first Analytics runtime is approved only for this DEV project/region."
    }
  }
}
resource "google_project_iam_member" "analytics_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.analytics.email}"
}
resource "google_bigquery_table_iam_member" "analytics_core_reader" {
  for_each   = local.analytics_core_read_tables
  project    = var.project_id
  dataset_id = "up_core"
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.analytics.email}"
}
resource "google_bigquery_table_iam_member" "analytics_writer" {
  for_each   = local.analytics_write_tables
  project    = var.project_id
  dataset_id = "up_analytics"
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.analytics.email}"
}
resource "google_cloud_run_v2_job" "analytics" {
  name                = "up-analytics-dev"
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.analytics.email
      max_retries     = 0
      timeout         = "3600s"
      containers {
        image   = var.analytics_image
        command = ["python", "-m", "src.analytics.job"]
        args = [
          "--live", "--confirm-project", "up-data-intelligence-dev",
          "--confirm-store", "mx-fashion", "--store", "mx-fashion",
          "--policy", "config/analytics/mx-fashion.dev.json",
          "--from", "2026-09-01", "--to", "2026-09-28",
          "--as-of", "2026-09-28T03:00:00Z",
          "--project", "up-data-intelligence-dev", "--location", "southamerica-east1",
          "--maximum-bytes-billed", tostring(var.analytics_maximum_bytes_billed),
          "--timeout-seconds", "300", "--full-refresh", "--confirm-backfill-complete"
        ]
        resources {
          limits = { cpu = "2", memory = "4Gi" }
        }
      }
    }
  }
  depends_on = [google_project_iam_member.analytics_jobs, google_bigquery_table_iam_member.analytics_core_reader, google_bigquery_table_iam_member.analytics_writer]
}
