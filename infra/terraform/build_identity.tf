# Dedicated DEV build identity; no runtime, data or Secret Manager access.
variable "build_submitter_member" {
  description = "Approved user allowed to submit builds as the dedicated build service account."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^user:[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.build_submitter_member))
    error_message = "Provide the approved user:email principal; no public or group principal."
  }
}

resource "google_service_account" "build" {
  project      = var.project_id
  account_id   = "up-build-${var.environment}"
  display_name = "UP DEV container build; no runtime or credential keys"
  lifecycle {
    precondition {
      condition     = var.project_id == "up-data-intelligence-dev" && var.environment == "dev" && var.region == "southamerica-east1"
      error_message = "Build infrastructure is approved only for the existing DEV project and region."
    }
  }
  depends_on = [google_project_service.required]
}

resource "google_service_account_iam_member" "build_submitter" {
  service_account_id = google_service_account.build.name
  role               = "roles/iam.serviceAccountUser"
  member             = var.build_submitter_member
}

resource "google_project_iam_member" "build_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.build.email}"
}

# The existing repository is managed in the independent registry root/state.
resource "google_artifact_registry_repository_iam_member" "build_writer" {
  project    = var.project_id
  location   = var.region
  repository = "up-data-intelligence"
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.build.email}"
}

resource "google_storage_bucket" "build_source" {
  project                     = var.project_id
  name                        = "${var.project_id}-876521886531-build-source"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = { application = "up-data-intelligence", environment = var.environment, purpose = "build-source" }
  versioning { enabled = false }
  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 7 }
  }
  lifecycle { prevent_destroy = true }
  depends_on = [google_service_account.build]
}

resource "google_storage_bucket_iam_member" "build_source_viewer" {
  bucket = google_storage_bucket.build_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.build.email}"
}
