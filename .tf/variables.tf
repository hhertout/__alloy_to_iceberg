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