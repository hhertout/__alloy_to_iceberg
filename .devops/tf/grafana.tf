resource "grafana_folder" "dl_obs" {
  title = "DL Obs"
}

resource "grafana_dashboard" "dl_obs" {
  folder    = grafana_folder.dl_obs.id
  overwrite = true

  config_json = file("${path.module}/grafana/dashboard.json")
}
