# Independent root/state: no jobs, secrets, datasets or dependency on var.image.
resource "google_project_service" "artifact_registry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}
resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = var.repository_id
  description   = "UP Data Intelligence ${var.environment} container images"
  format        = "DOCKER"
  labels        = { environment = var.environment, application = "up-data-intelligence" }
  docker_config { immutable_tags = true }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.artifact_registry]
}
resource "google_artifact_registry_repository_iam_member" "publishers" {
  for_each   = var.publisher_members
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = each.value
}
resource "google_artifact_registry_repository_iam_member" "deployers" {
  for_each   = var.deployer_members
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.reader"
  member     = each.value
}
# Same-project Cloud Run pulls via its Google-managed service agent and
# roles/run.serviceAgent, established when Run API is enabled by the jobs root.
# The application's runtime service account does not need registry permissions.
