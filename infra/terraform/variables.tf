variable "project_id" { type = string }
variable "region" { type = string }
variable "dataset_location" { type = string }
variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Use dev, staging ou prod; projeto GCP distinto por ambiente."
  }
}
variable "image" {
  type = string
  validation {
    condition     = can(regex("@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Forneça imagem já publicada, fixada por digest."
  }
}
variable "lease_bucket_name" { type = string }
variable "lease_bucket_location" { type = string }
variable "secret_id" {
  type        = string
  description = "ID do container de Secret Manager gerenciado neste projeto. Versões e valores são gerenciados fora do Terraform."
}
variable "secret_version" {
  type    = string
  default = "latest"
}
variable "pilot" {
  type = object({
    store_id                       = string
    store_name                     = string
    store_slug                     = string
    timezone                       = string
    connection_id                  = string
    upzero_store_identifier        = optional(string)
    initial_from                   = string
    purchase_order_id_effective_at = optional(string)
    facts_lookback_hours           = optional(number, 72)
    orders_lookback_days           = optional(number, 30)
    stale_after_minutes            = optional(number, 60)
  })
}
variable "schedules" {
  type = map(string)
  default = {
    sync      = "*/15 * * * *"
    reconcile = "0 3 * * *"
    quality   = "*/30 * * * *"
  }
}
variable "scheduler_paused" {
  type    = bool
  default = true
}
variable "raw_retention_days" {
  type = number
  validation {
    condition     = var.raw_retention_days >= 1
    error_message = "A retenção RAW deve ser decidida explicitamente."
  }
}
variable "deletion_protection" {
  type    = bool
  default = true
}
