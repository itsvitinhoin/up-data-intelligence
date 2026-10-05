# CHANGE #19.3B: additive table-scoped access, disabled until saved-plan review.
# No scheduler, source identity, policy, secret version or capacity change here.
variable "dashboard_completion_enabled" {
  description = "Enable only after review of the #19.3B catalog/creative/extension permissions."
  type        = bool
  default     = false
}
variable "dashboard_completion_automatic_enrichment" {
  description = "Start bounded current catalog/ad enrichment only after the scoped runtime is verified."
  type        = bool
  default     = false
}
variable "dashboard_completion_health_enrichment" {
  description = "Require catalog/ad Health proofs only after current completion evidence exists."
  type        = bool
  default     = false
}
locals {
  completion_catalog_reads = toset([
    "catalog_observations", "catalog_products_versions", "catalog_variants_versions",
    "catalog_attributes_versions", "catalog_inventory_versions"
  ])
  completion_extensions = toset(["installation_extension_plans", "installation_extension_work_units"])
  completion_read_permissions = merge(
    { for table in setunion(local.completion_catalog_reads, toset(["meta_account_bindings", "meta_live_ads", "meta_creative_insights_daily"])) : "product-read/${table}" => {
      table = table, member = "serviceAccount:${local.product_enabled ? google_service_account.product["read"].email : "disabled"}", write = false
    } },
    { for table in toset(["installation_plans", "installation_work_units", "sync_checkpoints", "sync_runs", "analytics_publications", "analytics_store_daily", "analytics_funnel_daily"]) : "product-admin/${table}" => {
      table = table, member = "serviceAccount:${local.product_enabled ? google_service_account.product["admin"].email : "disabled"}", write = false
    } },
    { for item in flatten([for principal in ["dispatcher", "upzero", "meta", "analytics", "intelligence"] : [for table in local.completion_extensions : {
      principal = principal, table = table
      } if table != "installation_extension_work_units" || contains(["dispatcher", "intelligence"], principal)]]) : "normal-${item.principal}/${item.table}" => {
      table = item.table, member = "serviceAccount:${google_service_account.control_plane[item.principal].email}", write = false
    } },
    { for table in local.completion_extensions : "installation-orchestrator/${table}" => {
      table = table, member = "serviceAccount:${google_service_account.installation_orchestrator.email}", write = true
    } },
    { for table in local.completion_catalog_reads : "health/${table}" => {
      table = table, member = "serviceAccount:${var.data_health_image != null ? google_service_account.data_health[0].email : "disabled"}", write = false
    } }
  )
  completion_write_permissions = merge(
    { for table in setunion(local.completion_extensions, toset(["integration_operations"])) : "admin/${table}" => {
      table = table, member = "serviceAccount:${local.product_enabled ? google_service_account.product["admin"].email : "disabled"}", write = true
    } },
    { for principal in ["upzero", "meta", "analytics"] : "worker-${principal}/installation_extension_work_units" => {
      table = "installation_extension_work_units", member = "serviceAccount:${google_service_account.control_plane[principal].email}", write = true
    } },
    { for table in ["meta_creative_insights_daily", "meta_creative_insights_daily_versions"] : "meta/${table}" => {
      table = table, member = "serviceAccount:${google_service_account.control_plane["meta"].email}", write = true
    } },
    { "analytics/store_runtime_config" = {
      table = "store_runtime_config", member = "serviceAccount:${google_service_account.control_plane["analytics"].email}", write = true
    } }
  )
  completion_permissions = var.dashboard_completion_enabled ? merge(local.completion_read_permissions, local.completion_write_permissions) : {}
}
resource "google_bigquery_table_iam_member" "dashboard_completion" {
  for_each   = local.completion_permissions
  project    = var.project_id
  dataset_id = local.tables[each.value.table].dataset
  table_id   = google_bigquery_table.tables[each.value.table].table_id
  role       = each.value.write ? google_project_iam_custom_role.control_plane_writer.name : "roles/bigquery.dataViewer"
  member     = each.value.member
  lifecycle {
    precondition {
      condition     = local.product_enabled && var.installation_image != null && var.data_health_image != null
      error_message = "Completion requires the already approved private product, Installation and Health runtimes."
    }
  }
}
# Existing Admin namespace covers UP Zero rotations. Meta uses only the global
# pinned reference, never per-store tokens; this additional grant requires review.
variable "dashboard_completion_admin_meta_probe" {
  description = "Separate Stage 2 approval for Admin to probe the existing global Meta credential."
  type        = bool
  default     = false
}
resource "google_secret_manager_secret_iam_member" "completion_admin_meta_probe" {
  count     = var.dashboard_completion_admin_meta_probe && var.dashboard_completion_enabled && local.product_enabled ? 1 : 0
  project   = var.project_id
  secret_id = google_secret_manager_secret.change16_meta.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.product["admin"].email}"
}

# Keep the production frontend's existing private APIs pinned. Only the reviewed
# Vercel Preview is configured to call these authenticated DEV application services.
variable "dashboard_completion_preview_image" {
  type     = string
  default  = null
  nullable = true
  validation {
    condition     = var.dashboard_completion_preview_image == null ? true : can(regex("^southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/product-api@sha256:[a-f0-9]{64}$", var.dashboard_completion_preview_image))
    error_message = "An immutable approved DEV product image digest is required."
  }
}
resource "google_cloud_run_v2_service" "completion_preview_api" {
  for_each             = var.dashboard_completion_preview_image == null ? toset([]) : toset(["read", "admin"])
  name                 = "up-${each.key}-api-data-preview"
  location             = var.region
  deletion_protection  = true
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  template {
    service_account                  = google_service_account.product[each.key].email
    timeout                          = "120s"
    max_instance_request_concurrency = 8
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image   = var.dashboard_completion_preview_image
      command = ["gunicorn"]
      args    = ["--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "--access-logfile", "/dev/null", "src.product_auth.runtime:${each.key}_app()"]
      ports { container_port = 8080 }
      resources { limits = { cpu = "1", memory = "1Gi" } }
      dynamic "env" {
        for_each = merge({
          UP_PRODUCT_PROJECT = var.project_id, UP_PRODUCT_LOCATION = var.region
          }, each.key == "read" ? {
          UP_PRODUCT_CATALOG_ENABLED = "1", UP_PRODUCT_CREATIVES_ENABLED = "1"
          } : {
          UP_INSTALLATION_EXTENSIONS_ENABLED = "1",
          UP_PRODUCT_PROJECT_NUMBER          = tostring(data.google_project.control_plane.number),
          UP_PRODUCT_LEASE_BUCKET            = var.lease_bucket_name,
          UP_PRODUCT_SUBJECT_KEY             = var.product_subject_key,
          UP_META_SECRET_REFERENCE           = "projects/${var.project_id}/secrets/${var.change16_meta_secret_id}/versions/${var.control_plane_meta_secret_version}"
        })
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
  lifecycle {
    precondition {
      condition     = var.dashboard_completion_enabled && var.dashboard_completion_admin_meta_probe && local.product_enabled && var.product_vercel_enabled && var.product_subject_key != null && var.control_plane_meta_secret_version != null
      error_message = "Preview serving requires reviewed scoped access and the existing pinned credentials."
    }
  }
  depends_on = [google_bigquery_table_iam_member.dashboard_completion, google_secret_manager_secret_iam_member.completion_admin_meta_probe]
}
resource "google_cloud_run_v2_service_iam_member" "completion_preview_invoker" {
  for_each = google_cloud_run_v2_service.completion_preview_api
  project  = var.project_id
  location = var.region
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.product_vercel[0].email}"
}
