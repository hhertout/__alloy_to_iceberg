resource "azurerm_resource_group" "default" {
  name     = "rg01-weste-torchdeeplearning"
  location = "West Europe"
}

resource "azurerm_storage_account" "default" {
  name                = var.sa_name
  resource_group_name = azurerm_resource_group.default.name
  location            = azurerm_resource_group.default.location

  account_tier             = "Standard"
  access_tier              = "Cool"
  account_replication_type = "LRS"

  is_hns_enabled                = true
  public_network_access_enabled = false
}

resource "azurerm_storage_container" "default" {
  name                  = var.container_name
  storage_account_id    = azurerm_storage_account.default.id
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.default.id

  rule {
    name    = "cool-to-cold-after-90days"
    enabled = true

    filters {
      prefix_match = ["iceberg/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        tier_to_cold_after_days_since_modification_greater_than    = 90
        delete_after_days_since_creation_greater_than = 365 * 2
      }

      snapshot {
        tier_to_cold_after_days_since_creation_greater_than = 90
        delete_after_days_since_creation_greater_than = 365 * 2
      }
    }
  }
}