variable "grafana_url" {
  type = string
  description = "Grafana URL"
}

variable "grafana_auth" {
  type = string
  description = "Grafana service account token"
}

variable "azure_subscription_id" {
  type        = string
  description = "Azure subscription ID"
}

variable "sa_name" {
  type        = string
  description = "Storage account name"
}

variable "container_name" {
  type        = string
  description = "Storage container name"
}