# Future trusted admin only. No service/job/scheduler or per-store IAM.
resource "google_bigquery_table_iam_member" "onboarding_admin_write" {
  for_each   = var.control_plane_admin_member == null ? toset([]) : toset(["source_connections", "meta_account_bindings", "workspace_store_bindings", "onboarding_operations"])
  project    = var.project_id
  dataset_id = local.tables[each.key].dataset
  table_id   = google_bigquery_table.tables[each.key].table_id
  role       = google_project_iam_custom_role.control_plane_writer.name
  member     = var.control_plane_admin_member
}
# Create is authorized at the project, so it cannot be restricted by secret resource name.
# Application enforcement is mandatory. All operations on existing secrets are conditional.
resource "google_project_iam_custom_role" "onboarding_secret_create" {
  count       = var.control_plane_admin_member == null ? 0 : 1
  role_id     = "upOnboardingSecretCreate_${var.environment}"
  title       = "Onboarding secret container creation"
  permissions = ["secretmanager.secrets.create"]
}
resource "google_project_iam_member" "onboarding_secret_create" {
  count   = var.control_plane_admin_member == null ? 0 : 1
  project = var.project_id
  role    = google_project_iam_custom_role.onboarding_secret_create[0].name
  member  = var.control_plane_admin_member
}
resource "google_project_iam_custom_role" "onboarding_secret_reconcile" {
  count       = var.control_plane_admin_member == null ? 0 : 1
  role_id     = "upOnboardingSecretReconcile_${var.environment}"
  title       = "Onboarding version write and reconciliation"
  permissions = ["secretmanager.secrets.get", "secretmanager.versions.add", "secretmanager.versions.list", "secretmanager.versions.access"]
}
resource "google_project_iam_member" "onboarding_secret_reconcile" {
  count   = var.control_plane_admin_member == null ? 0 : 1
  project = var.project_id
  role    = google_project_iam_custom_role.onboarding_secret_reconcile[0].name
  member  = var.control_plane_admin_member
  condition {
    title       = "OnboardingUPZeroNamespaceOnly"
    expression  = "resource.name.startsWith('projects/${data.google_project.control_plane.number}/secrets/up-intelligence-upzero-')"
    description = "Server enforces deterministic ownership and numeric versions. No deletion."
  }
}
