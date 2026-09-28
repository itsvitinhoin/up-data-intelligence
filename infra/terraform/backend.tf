# DEV only. Bucket must be provisioned separately by infra/terraform/bootstrap.
# Other environments require distinct backend configuration AND state.
terraform {
  backend "gcs" {
    bucket = "up-data-intelligence-dev-876521886531-tfstate"
    prefix = "foundation/dev"
  }
}
