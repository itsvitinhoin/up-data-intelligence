locals {
  tables   = jsondecode(file("${path.module}/tables.json"))
  datasets = toset(["up_raw", "up_core", "up_ops", "up_analytics"])
  config = merge(var.pilot, {
    environment          = var.environment
    project_id           = var.project_id
    location             = var.dataset_location
    lease_bucket         = var.lease_bucket_name
    secret_resource_name = "projects/${var.project_id}/secrets/${var.secret_id}/versions/${var.secret_version}"
  })
}
resource "google_project_service" "required" {
  for_each           = toset(["bigquery.googleapis.com", "run.googleapis.com", "cloudscheduler.googleapis.com", "secretmanager.googleapis.com", "storage.googleapis.com", "iam.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}
resource "google_bigquery_dataset" "layers" {
  for_each                   = local.datasets
  dataset_id                 = each.key
  location                   = var.dataset_location
  friendly_name              = "UP ${var.environment} ${each.key}"
  labels                     = { environment = var.environment, application = "up-data-intelligence" }
  delete_contents_on_destroy = false
  depends_on                 = [google_project_service.required]
}
resource "google_bigquery_table" "tables" {
  for_each            = local.tables
  dataset_id          = google_bigquery_dataset.layers[each.value.dataset].dataset_id
  table_id            = each.key
  deletion_protection = var.deletion_protection
  schema              = file("${path.module}/schemas/${each.key}.json")
  clustering          = each.value.cluster
  dynamic "time_partitioning" {
    for_each = each.value.partition == null ? [] : [each.value.partition]
    content {
      type          = "DAY"
      field         = time_partitioning.value
      expiration_ms = each.value.dataset == "up_raw" ? var.raw_retention_days * 86400000 : null
    }
  }
  # Corrected facts/orders may move partitions; key merges must see prior versions.
  require_partition_filter = false
}
resource "google_service_account" "runtime" {
  account_id   = "up-foundation-${var.environment}"
  display_name = "UP pilot ingestion and normalization"
  depends_on   = [google_project_service.required]
}
resource "google_service_account" "scheduler" {
  account_id = "up-scheduler-${var.environment}"
  depends_on = [google_project_service.required]
}
resource "google_project_iam_member" "job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}
resource "google_project_iam_custom_role" "data_writer" {
  role_id     = "upFoundationDataWriter_${var.environment}"
  title       = "UP scoped data reader/writer"
  permissions = ["bigquery.tables.get", "bigquery.tables.getData", "bigquery.tables.updateData", "bigquery.tables.update"]
}
resource "google_bigquery_dataset_iam_member" "writer" {
  for_each   = toset(["up_raw", "up_core", "up_ops"])
  dataset_id = google_bigquery_dataset.layers[each.key].dataset_id
  role       = google_project_iam_custom_role.data_writer.name
  member     = "serviceAccount:${google_service_account.runtime.email}"
}
# Container only. Secret versions are added outside Terraform, after approval.
resource "google_secret_manager_secret" "key" {
  project             = var.project_id
  secret_id           = var.secret_id
  labels              = { environment = var.environment, application = "up-data-intelligence" }
  deletion_protection = var.deletion_protection
  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.required]
}
resource "google_secret_manager_secret_iam_member" "key" {
  project    = google_secret_manager_secret.key.project
  secret_id  = google_secret_manager_secret.key.secret_id
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.runtime.email}"
  depends_on = [google_secret_manager_secret.key]
}
# Technical store-scoped mutex only. No source data, TTL, or automatic stale lock takeover.
resource "google_storage_bucket" "leases" {
  name                        = var.lease_bucket_name
  location                    = var.lease_bucket_location
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  depends_on                  = [google_project_service.required]
}
resource "google_project_iam_custom_role" "lease_writer" {
  role_id     = "upFoundationLeaseWriter_${var.environment}"
  title       = "UP create/delete generation-guarded lease"
  permissions = ["storage.objects.create", "storage.objects.delete", "storage.objects.get"]
}
resource "google_storage_bucket_iam_member" "lease" {
  bucket = google_storage_bucket.leases.name
  role   = google_project_iam_custom_role.lease_writer.name
  member = "serviceAccount:${google_service_account.runtime.email}"
}
resource "google_cloud_run_v2_job" "foundation" {
  for_each            = var.schedules
  name                = "up-foundation-${var.environment}-${each.key}"
  location            = var.region
  deletion_protection = var.deletion_protection
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.runtime.email
      max_retries     = 0
      timeout         = "3600s"
      containers {
        image = var.image
        args  = ["--live", "--confirm-store", var.pilot.store_id, "--mode", each.key, "--resource", "all"]
        env {
          name  = "UP_CONFIG_JSON"
          value = jsonencode(local.config)
        }
        resources { limits = { cpu = "1", memory = "1Gi" } }
      }
    }
  }
  depends_on = [google_bigquery_table.tables, google_bigquery_dataset_iam_member.writer, google_secret_manager_secret_iam_member.key, google_storage_bucket_iam_member.lease]
}
resource "google_cloud_run_v2_job_iam_member" "invoke" {
  for_each = google_cloud_run_v2_job.foundation
  name     = each.value.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}
resource "google_cloud_scheduler_job" "scheduled" {
  for_each  = var.schedules
  name      = "up-foundation-${var.environment}-${each.key}"
  region    = var.region
  schedule  = each.value
  time_zone = var.pilot.timezone
  paused    = var.scheduler_paused
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.foundation[each.key].name}:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.invoke]
}
