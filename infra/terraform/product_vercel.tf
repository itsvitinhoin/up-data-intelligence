# Additive DEV serving boundary. No data Jobs, schedules, business grants or key files.
variable "product_vercel_enabled" {
  type    = bool
  default = false
}
variable "product_vercel_preview_enabled" {
  description = "Separate preview federation scope: enable only after explicit review."
  type        = bool
  default     = false
}
variable "product_vercel_preview_domains" {
  description = "Exact reviewed preview hosts for Firebase Auth; no wildcard."
  type        = list(string)
  default     = []
  validation {
    condition     = alltrue([for host in var.product_vercel_preview_domains : can(regex("^up-data-intelligence-[a-z0-9-]+-victorcheunin-6445s-projects\\.vercel\\.app$", host))])
    error_message = "Only exact preview hosts of the existing canonical project are allowed."
  }
}
locals {
  vercel_environments = var.product_vercel_enabled ? toset(var.product_vercel_preview_enabled ? ["production", "preview"] : ["production"]) : toset([])
  vercel_owner        = "victorcheunin-6445s-projects"
  vercel_owner_id     = "team_t671r3SZj4i6JvObobazq9UH"
  vercel_project      = "up-data-intelligence"
  vercel_project_id   = "prj_97pqMmRY596f2PNg4ipCsA1r8Jbo"
}
resource "google_project_service" "product_vercel" {
  for_each           = var.product_vercel_enabled ? toset(["iamcredentials.googleapis.com", "sts.googleapis.com"]) : toset([])
  service            = each.key
  disable_on_destroy = false
}
resource "google_service_account" "product_vercel" {
  count        = var.product_vercel_enabled ? 1 : 0
  account_id   = "up-product-vercel-dev"
  display_name = "Existing Vercel frontend: private product API invocation only"
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = local.product_enabled && var.project_id == "up-data-intelligence-dev" && var.environment == "dev" && var.region == "southamerica-east1"
      error_message = "Vercel federation is authorized only for the existing DEV product APIs."
    }
  }
}
resource "google_iam_workload_identity_pool" "product_vercel" {
  count                     = var.product_vercel_enabled ? 1 : 0
  workload_identity_pool_id = "up-product-vercel-dev"
  display_name              = "UP Vercel product DEV"
  lifecycle { prevent_destroy = true }
}
resource "google_iam_workload_identity_pool_provider" "product_vercel" {
  for_each                           = local.vercel_environments
  workload_identity_pool_id          = google_iam_workload_identity_pool.product_vercel[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "up-product-vercel-${each.key}"
  display_name                       = "UP Vercel ${each.key}"
  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.owner_id"    = "assertion.owner_id"
    "attribute.project_id"  = "assertion.project_id"
    "attribute.environment" = "assertion.environment"
  }
  attribute_condition = "assertion.owner_id == '${local.vercel_owner_id}' && assertion.owner == '${local.vercel_owner}' && assertion.project_id == '${local.vercel_project_id}' && assertion.project == '${local.vercel_project}' && assertion.environment == '${each.key}' && assertion.sub == 'owner:${local.vercel_owner}:project:${local.vercel_project}:environment:${each.key}'"
  oidc {
    issuer_uri        = "https://oidc.vercel.com/${local.vercel_owner}"
    allowed_audiences = ["https://vercel.com/${local.vercel_owner}"]
  }
  depends_on = [google_project_service.product_vercel]
}
resource "google_service_account_iam_member" "product_vercel_federation" {
  for_each           = local.vercel_environments
  service_account_id = google_service_account.product_vercel[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/projects/${data.google_project.control_plane.number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.product_vercel[0].workload_identity_pool_id}/subject/owner:${local.vercel_owner}:project:${local.vercel_project}:environment:${each.key}"
  depends_on         = [google_iam_workload_identity_pool_provider.product_vercel]
}
resource "google_cloud_run_v2_service_iam_member" "product_vercel_invoker" {
  for_each = var.product_vercel_enabled ? google_cloud_run_v2_service.product_api : {}
  project  = var.project_id
  location = var.region
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.product_vercel[0].email}"
}
