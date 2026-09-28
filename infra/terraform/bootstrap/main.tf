# Independent local bootstrap state. Never reference this root from Foundation.
# Storage API and permissions of the bootstrap operator must already be available.
resource "google_storage_bucket" "tfstate" {
  project                     = var.project_id
  name                        = var.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels = {
    application = "up-data-intelligence"
    environment = var.environment
    purpose     = "terraform-state"
  }
  versioning { enabled = true }
  # Keep current objects indefinitely. Delete only old noncurrent generations,
  # and only when at least 20 newer generations exist (both conditions apply).
  lifecycle_rule {
    action { type = "Delete" }
    condition {
      with_state                 = "ARCHIVED"
      days_since_noncurrent_time = 365
      num_newer_versions         = 20
    }
  }
  soft_delete_policy { retention_duration_seconds = 604800 }
  lifecycle { prevent_destroy = true }
}
resource "google_storage_bucket_iam_member" "state_access" {
  for_each = var.state_members
  bucket   = google_storage_bucket.tfstate.name
  role     = "roles/storage.objectAdmin"
  member   = each.value
}
