output "state_bucket" { value = google_storage_bucket.tfstate.name }
output "foundation_state_uri" {
  value = "gs://${google_storage_bucket.tfstate.name}/foundation/dev/default.tfstate"
}
