output "storage_account_name" {
  value = "Storage account ${azurerm_storage_account.default.name} successfully created"
}

output "storage_container_name" {
  value = "Container ${azurerm_storage_container.default.name} successfully created"
}