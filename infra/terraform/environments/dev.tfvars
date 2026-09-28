# DEV: up-data-intelligence-dev (project number: 876521886531).
# Image and PILOT_STORE remain placeholders pending deployment preparation.
project_id            = "up-data-intelligence-dev"
environment           = "dev"
region                = "southamerica-east1"
dataset_location      = "southamerica-east1"
lease_bucket_name     = "up-data-intelligence-dev-876521886531-leases"
lease_bucket_location = "southamerica-east1"
image                 = "REPLACE_WITH_IMAGE@sha256:REPLACE_WITH_DIGEST"
secret_id             = "up-intelligence-upzero-pilot-store-api-key"
scheduler_paused      = true
raw_retention_days    = 365
pilot = {
  store_id                       = "PILOT_STORE"
  store_name                     = "Loja piloto"
  store_slug                     = "pilot-store"
  timezone                       = "America/Sao_Paulo"
  connection_id                  = "pilot-upzero"
  initial_from                   = "2026-09-01T00:00:00Z"
  purchase_order_id_effective_at = null
}
