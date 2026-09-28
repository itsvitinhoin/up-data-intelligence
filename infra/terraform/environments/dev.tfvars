# DEV: up-data-intelligence-dev (project number: 876521886531).
# Loja piloto MX Fashion; correção purchase/order_id ainda não confirmada.
project_id            = "up-data-intelligence-dev"
environment           = "dev"
region                = "southamerica-east1"
dataset_location      = "southamerica-east1"
lease_bucket_name     = "up-data-intelligence-dev-876521886531-leases"
lease_bucket_location = "southamerica-east1"
image                 = "southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:5e0e7b2fd567105853bae8b9ad2ae789a7dde0e3157113109b5b6ae4ffc860a2"
secret_id             = "up-intelligence-upzero-pilot-store-api-key"
scheduler_paused      = true
raw_retention_days    = 365
pilot = {
  store_id                       = "mx-fashion"
  store_name                     = "MX Fashion"
  store_slug                     = "mx-fashion"
  timezone                       = "America/Sao_Paulo"
  connection_id                  = "mx-fashion-upzero"
  initial_from                   = "2026-09-01T00:00:00Z"
  purchase_order_id_effective_at = null
}
