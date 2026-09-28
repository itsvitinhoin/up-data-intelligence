output "runtime_service_account" { value = google_service_account.runtime.email }
output "datasets" { value = keys(google_bigquery_dataset.layers) }
output "jobs" { value = { for mode, job in google_cloud_run_v2_job.foundation : mode => job.name } }
output "scheduler_paused" { value = var.scheduler_paused }
