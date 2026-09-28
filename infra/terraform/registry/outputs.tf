output "repository_name" { value = google_artifact_registry_repository.images.name }
output "image_path" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}/foundation"
}
