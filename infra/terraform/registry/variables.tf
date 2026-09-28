variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Use dev, staging ou prod em projetos separados."
  }
}
variable "repository_id" {
  type    = string
  default = "up-data-intelligence"
}
variable "publisher_members" {
  type        = set(string)
  default     = []
  description = "Identidades aprovadas (user:email/serviceAccount:email) para push local/CI. Writer somente neste repositório."
}
variable "deployer_members" {
  type        = set(string)
  default     = []
  description = "Identidades do deployment que precisam de Reader no repositório."
}
