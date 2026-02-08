terraform {
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "4.25.0"
    }

    azurerm = {
      source = "hashicorp/azurerm"
      version = "4.2.0"
    }
  }
}

provider "grafana" {
  url  = var.grafana_url
  auth = var.grafana_auth
}

provider "azurerm" {
  subscription_id = var.azure_subscription_id

  features {
  }
}