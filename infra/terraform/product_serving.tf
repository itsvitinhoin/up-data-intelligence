# Isolated additive DEV product serving. No data Jobs/Schedulers or business policies.
variable "product_api_image" {
  type     = string
  default  = null
  nullable = true
  validation {
    condition     = var.product_api_image == null ? true : can(regex("^southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/product-api@sha256:[a-f0-9]{64}$", var.product_api_image))
    error_message = "An immutable DEV product API digest is required."

  }
}
variable "product_web_image" {
  type     = string
  default  = null
  nullable = true
  validation {
    condition     = var.product_web_image == null ? true : can(regex("^southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/product-web@sha256:[a-f0-9]{64}$", var.product_web_image))
    error_message = "An immutable DEV product web digest is required."

  }
}
variable "product_subject_key" {
  description = "Private, stable onboarding HMAC key. Supplied from private deployment input; never a browser env."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
  validation {
    condition     = var.product_subject_key == null ? true : can(regex("^[a-f0-9]{64}$", var.product_subject_key))
    error_message = "A 32-byte private hex key is required."

  }
}
locals {
  product_enabled = var.product_api_image != null
  product_read_tables = toset([
    "store_runtime_config", "workspace_store_bindings", "installation_plans", "installation_work_units",
    "sync_checkpoints", "sync_runs", "source_connections", "customers", "orders",
    "analytics_publications", "analytics_store_daily", "analytics_customer_metrics",
    "analytics_customer_purchase_sequence", "analytics_cohorts", "analytics_purchase_distribution",
    "analytics_products_daily", "analytics_funnel_daily", "analytics_intelligence_publications",
    "analytics_customer_360_profile", "analytics_customer_journey_summary", "analytics_customer_orders_summary",
    "analytics_customer_paid_influence", "analytics_customer_products_summary", "analytics_customer_timeline",
    "analytics_order_paid_influence", "analytics_performance_summary", "analytics_campaign_performance_daily",
    "analytics_campaign_order_performance", "analytics_campaign_customer_performance"
  ])
  product_admin_tables = toset(["workspace_store_bindings", "store_runtime_config", "source_connections", "meta_account_bindings", "onboarding_operations"])
  product_table_grants = local.product_enabled ? merge(
    { for table in local.product_read_tables : "read/${table}" => {
      service = "read", table = table, write = false
    } },
    { for table in local.product_admin_tables : "admin/${table}" => {
      service = "admin", table = table, write = true
    } }
  ) : {}
}
resource "google_project_service" "product" {
  for_each           = local.product_enabled ? toset(["identitytoolkit.googleapis.com", "securetoken.googleapis.com", "apikeys.googleapis.com"]) : toset([])
  service            = each.key
  disable_on_destroy = false
}
resource "google_identity_platform_config" "product" {
  count              = local.product_enabled ? 1 : 0
  project            = var.project_id
  authorized_domains = concat(["${var.project_id}.firebaseapp.com"], var.product_web_image == null ? [] : [replace(google_cloud_run_v2_service.product_web[0].uri, "https://", "")])
  sign_in {
    allow_duplicate_emails = false
    email {
      enabled           = true
      password_required = true
    }
    anonymous {
      enabled = false
    }
    phone_number {
      enabled = false
    }

  }
  client {
    permissions {
      disabled_user_deletion = true
      disabled_user_signup   = false
    }

  }
  depends_on = [google_project_service.product]
}
resource "google_apikeys_key" "product_auth" {
  count        = local.product_enabled ? 1 : 0
  name         = "up-product-auth-dev"
  display_name = "Public Firebase Auth client config; identity APIs only"
  restrictions {
    api_targets {
      service = "identitytoolkit.googleapis.com"
    }
    api_targets {
      service = "securetoken.googleapis.com"
    }

  }
  depends_on = [google_project_service.product]
}
resource "google_bigquery_table" "principal_access" {
  count               = local.product_enabled ? 1 : 0
  dataset_id          = google_bigquery_dataset.layers["up_ops"].dataset_id
  table_id            = "principal_access"
  schema              = file("${path.module}/product_schemas/principal_access.json")
  clustering          = ["identity_hash", "tenant_id"]
  deletion_protection = true
}
resource "google_service_account" "product" {
  for_each     = local.product_enabled ? toset(["read", "admin", "web"]) : toset([])
  account_id   = "up-product-${each.key}-dev"
  display_name = "UP DEV product ${each.key} boundary"
  lifecycle {
    precondition {
      condition     = var.project_id == "up-data-intelligence-dev" && var.environment == "dev" && var.region == "southamerica-east1"
      error_message = "Product serving is authorized only in DEV."

    }

  }
}
resource "google_project_iam_member" "product_query" {
  for_each = local.product_enabled ? toset(["read", "admin"]) : toset([])
  project  = var.project_id
  role     = "roles/bigquery.jobUser"
  member   = "serviceAccount:${google_service_account.product[each.key].email}"
}
resource "google_bigquery_table_iam_member" "product_tables" {
  for_each   = local.product_table_grants
  project    = var.project_id
  dataset_id = local.tables[each.value.table].dataset
  table_id   = google_bigquery_table.tables[each.value.table].table_id
  role       = each.value.write ? google_project_iam_custom_role.control_plane_writer.name : "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.product[each.value.service].email}"
}
resource "google_bigquery_table_iam_member" "product_access" {
  for_each   = local.product_enabled ? toset(["read", "admin"]) : toset([])
  project    = var.project_id
  dataset_id = "up_ops"
  table_id   = google_bigquery_table.principal_access[0].table_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.product[each.key].email}"
}
# No broad Firebase Admin role. Session APIs require only these three permissions.
resource "google_project_iam_custom_role" "product_firebase" {
  for_each    = local.product_enabled ? toset(["read", "admin"]) : toset([])
  role_id     = "upProductFirebase${title(each.key)}_dev"
  title       = "UP product ${each.key} session verifier"
  permissions = each.key == "read" ? ["firebaseauth.users.get"] : ["firebaseauth.users.get", "firebaseauth.users.createSession", "firebaseauth.users.update"]
}
resource "google_project_iam_member" "product_firebase" {
  for_each = google_project_iam_custom_role.product_firebase
  project  = var.project_id
  role     = each.value.name
  member   = "serviceAccount:${google_service_account.product[each.key].email}"
}
# Reuse #18.2 privileges. Its optional legacy admin roles may not exist in DEV;
# create identical product-owned roles then, without enabling any legacy admin grants.
resource "google_project_iam_custom_role" "product_onboarding_create" {
  count       = local.product_enabled && var.control_plane_admin_member == null ? 1 : 0
  role_id     = "upProductOnboardingCreate_dev"
  title       = "Product onboarding secret container creation"
  permissions = ["secretmanager.secrets.create"]
}
resource "google_project_iam_custom_role" "product_onboarding_reconcile" {
  count       = local.product_enabled && var.control_plane_admin_member == null ? 1 : 0
  role_id     = "upProductOnboardingReconcile_dev"
  title       = "Product onboarding version write and reconciliation"
  permissions = ["secretmanager.secrets.get", "secretmanager.versions.add", "secretmanager.versions.list", "secretmanager.versions.access"]
}
resource "google_project_iam_member" "product_secret_create" {
  count   = local.product_enabled ? 1 : 0
  project = var.project_id
  role    = var.control_plane_admin_member == null ? google_project_iam_custom_role.product_onboarding_create[0].name : google_project_iam_custom_role.onboarding_secret_create[0].name
  member  = "serviceAccount:${google_service_account.product["admin"].email}"
}
resource "google_project_iam_member" "product_secret_reconcile" {
  count   = local.product_enabled ? 1 : 0
  project = var.project_id
  role    = var.control_plane_admin_member == null ? google_project_iam_custom_role.product_onboarding_reconcile[0].name : google_project_iam_custom_role.onboarding_secret_reconcile[0].name
  member  = "serviceAccount:${google_service_account.product["admin"].email}"
  condition {
    title      = "ProductOnboardingUPZeroNamespaceOnly"
    expression = "resource.name.startsWith('projects/${data.google_project.control_plane.number}/secrets/up-intelligence-upzero-')"

  }
}
resource "google_storage_bucket_iam_member" "product_admin_lease" {
  count  = local.product_enabled ? 1 : 0
  bucket = google_storage_bucket.leases.name
  role   = google_project_iam_custom_role.lease_writer.name
  member = "serviceAccount:${google_service_account.product["admin"].email}"
  condition {
    title      = "ProductOnboardingLeasesOnly"
    expression = "resource.name.startsWith('projects/_/buckets/${google_storage_bucket.leases.name}/objects/leases/')"

  }
}
resource "google_cloud_run_v2_service" "product_api" {
  for_each             = local.product_enabled ? toset(["read", "admin"]) : toset([])
  name                 = "up-${each.key}-api"
  location             = var.region
  deletion_protection  = true
  ingress              = "INGRESS_TRAFFIC_ALL" # IAM required; web reaches the private run.app audience.
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
      image   = var.product_api_image
      command = ["gunicorn"]
      args    = ["--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "--access-logfile", "/dev/null", "src.product_auth.runtime:${each.key}_app()"]
      ports {
        container_port = 8080
      }
      resources {
        limits = { cpu = "1", memory = "1Gi"
        }
      }
      env {
        name  = "UP_PRODUCT_PROJECT"
        value = var.project_id
      }
      env {
        name  = "UP_PRODUCT_LOCATION"
        value = var.region
      }
      dynamic "env" {
        for_each = each.key == "admin" ? { UP_PRODUCT_PROJECT_NUMBER = tostring(data.google_project.control_plane.number), UP_PRODUCT_LEASE_BUCKET = var.lease_bucket_name, UP_PRODUCT_SUBJECT_KEY = var.product_subject_key
        } : {}
        content {
          name  = env.key
          value = env.value
        }

      }

    }

  }
  lifecycle {
    precondition {
      condition     = var.product_subject_key != null
      error_message = "Private subject key is required."

    }

  }
  depends_on = [google_project_service.product, google_bigquery_table_iam_member.product_tables, google_bigquery_table_iam_member.product_access, google_project_iam_member.product_query, google_project_iam_member.product_firebase, google_project_iam_member.product_secret_create, google_project_iam_member.product_secret_reconcile, google_storage_bucket_iam_member.product_admin_lease]
}
resource "google_cloud_run_v2_service_iam_member" "product_private" {
  for_each = google_cloud_run_v2_service.product_api
  project  = var.project_id
  location = var.region
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.product["web"].email}"
}
# Stage 2 only; absent while private API isolation acceptance is pending.
resource "google_cloud_run_v2_service" "product_web" {
  count                = var.product_web_image == null ? 0 : 1
  name                 = "up-web"
  location             = var.region
  deletion_protection  = true
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  template {
    service_account                  = google_service_account.product["web"].email
    timeout                          = "120s"
    max_instance_request_concurrency = 40
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.product_web_image
      ports {
        container_port = 8080
      }
      resources {
        limits = { cpu = "1", memory = "1Gi"
        }
      }
      env {
        name  = "DASHBOARD_DATA_MODE"
        value = "live"
      }
      env {
        name  = "UP_READ_SERVICE_URL"
        value = google_cloud_run_v2_service.product_api["read"].uri
      }
      env {
        name  = "UP_ADMIN_SERVICE_URL"
        value = google_cloud_run_v2_service.product_api["admin"].uri
      }
      env {
        name  = "UP_FIREBASE_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "UP_FIREBASE_API_KEY"
        value = google_apikeys_key.product_auth[0].key_string
      }

    }

  }
  lifecycle {
    precondition {
      condition     = local.product_enabled
      error_message = "Private product APIs must be deployed and accepted before web."

    }

  }
  depends_on = [google_cloud_run_v2_service_iam_member.product_private]
}
resource "google_cloud_run_v2_service_iam_member" "product_web_public" {
  count    = var.product_web_image == null ? 0 : 1
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.product_web[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
