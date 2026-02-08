resource "azurerm_resource_group" "default" {
  name     = "rg01-weste-torchdeeplearning"
  location = "West Europe"
}

resource "azurerm_storage_account" "default" {
  name                = "sa01torchdeeplearning"
  resource_group_name = azurerm_resource_group.default.name
  location            = azurerm_resource_group.default.location

  account_tier             = "Standard"
  access_tier              = "Cool"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "default" {
  name                  = "sac01-lts-obsdata"
  storage_account_name  = azurerm_storage_account.default.name
  container_access_type = "private"
}
