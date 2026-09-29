# STANDALONE PROPOSAL. Not referenced by the active Terraform root. DO NOT APPLY.
terraform {
  required_version = "~> 1.16.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "8.4.0"
    }
  }
}
variable "project_id" { type = string }
variable "region" { type = string }
variable "image" { type = string }
# Must remain false until live CLI, parity, watermark and policies are approved.
variable "enable_job_proposal" {
  type    = bool
  default = false
}
provider "google" {
  project = var.project_id
  region  = var.region
}
locals {
  analytics_tables = merge(jsondecode(file("${path.module}/tables.json")), {
    analytics_publications = { dataset = "up_analytics", partition = null, cluster = ["store_id", "policy_hash", "record_kind"] }
  })
  core_inputs = toset(["customers", "orders", "order_items", "analytics_events", "customers_versions", "orders_versions", "order_items_versions", "analytics_events_versions"])
}
resource "google_service_account" "analytics" {
  account_id   = "up-analytics-dev"
  display_name = "Analytics DEV proposed"
}
resource "google_bigquery_table" "analytics" {
  for_each            = local.analytics_tables
  dataset_id          = "up_analytics" # existing dataset, not recreated
  table_id            = each.key
  schema              = file("${path.module}/schemas/${each.key}.json")
  clustering          = each.value.cluster
  deletion_protection = true
  dynamic "time_partitioning" {
    for_each = each.value.partition == null ? [] : [each.value.partition]
    content {
      type  = "DAY"
      field = time_partitioning.value
    }
  }
  lifecycle { prevent_destroy = true }
}
resource "google_bigquery_table_iam_member" "core_reader" {
  for_each   = local.core_inputs
  project    = var.project_id
  dataset_id = "up_core"
  table_id   = each.key
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.analytics.email}"
}
resource "google_bigquery_table_iam_member" "analytics_writer" {
  for_each   = google_bigquery_table.analytics
  project    = var.project_id
  dataset_id = "up_analytics"
  table_id   = each.value.table_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.analytics.email}"
}
resource "google_project_iam_member" "jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.analytics.email}"
}
resource "google_cloud_run_v2_job" "analytics" {
  count    = var.enable_job_proposal ? 1 : 0
  name     = "up-analytics-dev"
  location = var.region
  deletion_protection = true
  template {
    task_count = 1
    template {
      service_account = google_service_account.analytics.email
      max_retries     = 0
      timeout         = "1800s"
      containers {
        image   = var.image
        command = ["python", "-m", "src.analytics.job"]
        args    = ["--help"] # deliberately not a runnable live configuration
      }
    }
  }
}
resource "google_service_account" "scheduler" {
  count      = var.enable_job_proposal ? 1 : 0
  account_id = "up-analytics-scheduler-dev"
}
resource "google_cloud_run_v2_job_iam_member" "invoke" {
  count    = var.enable_job_proposal ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.analytics[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler[0].email}"
}
resource "google_cloud_scheduler_job" "analytics" {
  count     = var.enable_job_proposal ? 1 : 0
  name      = "up-analytics-dev-proposed"
  region    = var.region
  schedule  = "0 6 * * *" # placeholder, not approved commercial schedule
  time_zone = "America/Sao_Paulo"
  paused    = true
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.analytics[0].name}:run"
    oauth_token { service_account_email = google_service_account.scheduler[0].email }
  }
}
