# DEV: up-data-intelligence-dev (project number: 876521886531).
# Loja piloto MX Fashion; correção purchase/order_id ainda não confirmada.
project_id            = "up-data-intelligence-dev"
environment           = "dev"
region                = "southamerica-east1"
dataset_location      = "southamerica-east1"
lease_bucket_name     = "up-data-intelligence-dev-876521886531-leases"
lease_bucket_location = "southamerica-east1"
image                 = "southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:52732474ca926b7b1e14765cfbe14cab90fc18ae2cdd9a6a01247dd7aeffa9c5"
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

analytics_image                      = "southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:ef816b9ae1f63f19b50fba7826d27ebd42482008ae2f17089be037abb10a707e"
analytics_maximum_bytes_billed       = 1073741824
analytics_maximum_total_bytes_billed = 137438953472

build_submitter_member = "user:upagency.oficial@gmail.com"

control_plane_image               = "southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:47e4ce9ecd849642950fecff6e0a6ab88756e9cba04c9729c20dacbcd9dfcd2e"
control_plane_meta_secret_version = "1"
installation_image                = "southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:5e9b3d0752cd78abfabf580b39c69eedf487dd72b086c3e62f6f593ccc2288f0"
