variable "project_id" { type = string }
variable "region" { type = string }
variable "bucket_name" { type = string }
variable "environment" {
  type = string
  validation {
    condition     = var.environment == "dev" && var.project_id == "up-data-intelligence-dev"
    error_message = "Este bootstrap é exclusivo do projeto DEV aprovado."
  }
}
variable "state_members" {
  type        = set(string)
  default     = []
  description = "Identidades existentes/aprovadas do Terraform; Object Admin somente neste bucket."
  validation {
    condition     = alltrue([for member in var.state_members : can(regex("^(user|serviceAccount):[^@ ]+@[^ ]+$", member))])
    error_message = "Informe somente user:email ou serviceAccount:email; acesso público não é permitido."
  }
}
