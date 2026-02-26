# Local development stack

This document describes how to set up and use the local observability stack for testing and debugging the project.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker Compose                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────┐      metrics      ┌────────────┐                  │
│   │  Alloy  │ ─────────────────►│ Prometheus │                  │
│   │ :12345  │                   │   :9090    │                  │
│   └────┬────┘                   └─────┬──────┘                  │
│        │                              ▲                         │
│        │ logs               metrics   │                         │
│        ▼                    (scrape)  │                         │
│   ┌─────────┐              ┌──────────┴──┐                      │
│   │  Loki   │              │  cAdvisor   │                      │
│   │ :3100   │              │   :8080     │                      │
│   └────┬────┘              └─────────────┘                      │
│        │                         │                              │
│        └──────────┬──────────────┘                              │
│                   ▼                                             │
│             ┌──────────┐                                        │
│             │ Grafana  │                                        │
│             │  :3000   │                                        │
│             └──────────┘                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Services

| Service | Port | Description | UI |
|---------|------|-------------|-----|
| Grafana | 3000 | Dashboard visualization | http://localhost:3000 |
| Alloy | 12345 | Telemetry collector | http://localhost:12345 |
| Prometheus | 9090 | Metrics database | http://localhost:9090 |
| Loki | 3100 | Logs database | - |
| cAdvisor | 8080 | Container metrics exporter | http://localhost:8080 |
| Polaris | 8181 / 8182 | Iceberg catalog (API / management) | - |

## Quick start

Before you begin, ensure you have the following:

- Docker & Docker Compose
- Make (optional)

### Start the stack

```sh
# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# View logs for a specific service
docker compose logs -f alloy
```

### Stop the stack

```sh
# Stop without deleting data
docker compose down

# Stop and delete volumes (full reset)
docker compose down -v
```

## Service configuration

### Alloy (`.docker/conf.alloy`)

Alloy is configured for:
- **Self-monitoring:** Scrapes its own metrics via `prometheus.exporter.self`.
- **Logs:** Sends internal logs to Loki via the `logging` block.
- **Remote write:** Pushes metrics to Prometheus.

```alloy
// Logs → Loki
logging {
  level    = "info"
  format   = "json"
  write_to = [loki.write.loki.receiver]
}

// Metrics → Prometheus
prometheus.exporter.self "alloy" {}
prometheus.scrape "alloy_internal" {
  targets    = prometheus.exporter.self.alloy.targets
  forward_to = [prometheus.remote_write.prom.receiver]
}
```

### Prometheus (`.docker/prometheus.yml`)

Prometheus is configured for:
- **Remote write receiver:** Enabled to receive metrics from Alloy.
- **Self-scraping:** Scrapes itself for monitoring.
- **cAdvisor scraping:** Scrapes container-level metrics from cAdvisor.

### cAdvisor

Exposes container resource usage metrics (CPU, memory, network, filesystem) for all running Docker containers. Prometheus scrapes it on the `cadvisor` job. Metrics are prefixed with `container_` (e.g. `container_cpu_usage_seconds_total`, `container_memory_usage_bytes`).

### Loki (`.docker/loki.yaml`)

Loki is configured for:
- **Mode:** Standalone (monolithic).
- **Storage:** Local filesystem.
- **Schema:** v13 (TSDB).
- **Auth:** Disabled for local development.

## Accessing interfaces

You can access the following service UIs.

### Grafana

- **URL**: http://localhost:3000
- **Login**: admin / admin

#### Adding datasources

1. **Prometheus**
   - Configuration → Data sources → Add data source
   - Type: Prometheus
   - URL: `http://prometheus:9090`

2. **Loki**
   - Configuration → Data sources → Add data source
   - Type: Loki
   - URL: `http://loki:3100`

### Prometheus

- **URL**: http://localhost:9090
- **Useful queries**:
  ```promql
  # Alloy info
  alloy_build_info

  # Scraping metrics
  prometheus_scrape_duration_seconds

  # Remote write stats
  prometheus_remote_write_samples_total
  ```

### Alloy

- **URL**: http://localhost:12345
- **Useful endpoints**:
  - `/metrics` - Prometheus metrics
  - `/ready` - Health check
  - `/graph` - Pipeline debug UI

## Test queries

You can use the following queries to verify the stack is working.

### Prometheus (metrics)

```promql
# Alloy version
alloy_build_info

# Number of active series
prometheus_tsdb_head_series

# Samples received via remote write
prometheus_remote_storage_samples_total
```

### Loki (logs)

```logql
# All Alloy logs
{job="alloy"}

# Logs with errors
{job="alloy"} |= "error"

# Parsed JSON logs
{job="alloy"} | json | level="error"

# Count by log level
sum by (level) (count_over_time({job="alloy"} | json [5m]))
```

## Debugging

### Verify Alloy is working

```sh
# Health check
curl http://localhost:12345/ready

# Exposed metrics
curl http://localhost:12345/metrics | head -50

# Active config (debug)
curl http://localhost:12345/-/config
```

### Verify Prometheus

```sh
# Health check
curl http://localhost:9090/-/healthy

# Active targets
curl http://localhost:9090/api/v1/targets | jq .

# Test a query
curl 'http://localhost:9090/api/v1/query?query=up' | jq .
```

### Verify Loki

```sh
# Health check
curl http://localhost:3100/ready

# Available labels
curl http://localhost:3100/loki/api/v1/labels | jq .

# Query recent logs
curl -G http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={job="alloy"}' \
  --data-urlencode 'limit=10' | jq .
```

### Common issues

#### Alloy won't start
```sh
# Check config syntax
docker compose exec alloy alloy fmt /etc/alloy/conf.alloy

# View errors
docker compose logs alloy
```

#### Prometheus not receiving metrics
```sh
# Check remote write is enabled
docker compose logs prometheus | grep -i remote

# Check targets in UI
# http://localhost:9090/targets
```

#### Loki not receiving logs
```sh
# Check connection
docker compose exec alloy wget -q -O- http://loki:3100/ready

# Check ingestion errors
docker compose logs loki | grep -i error
```

## Python code integration

You can test the Grafana client against the local stack.

### Testing GrafanaDao

```python
import os
os.environ["GRAFANA_URL"] = "http://localhost:3000"
os.environ["GRAFANA_SA_TOKEN"] = "your-service-account-token"

from src.data.grafana import GrafanaDao
from src.data.grafana_dto import DatasourceKind

dao = GrafanaDao()

# Query Prometheus via Grafana
response = dao.query(
    kind=DatasourceKind.PROMETHEUS,
    datasource_uid="prometheus-uid",  # Find in Grafana UI
    expr='alloy_build_info',
)
print(response.get_values())
```

### Creating a Grafana service account

1. Grafana → Administration → Service accounts
2. Add service account → Name: "dev-local"
3. Add token → Copy the token
4. Add to `.env`:
   ```sh
   GRAFANA_URL=http://localhost:3000
   GRAFANA_SA_TOKEN=<token>
   ```

## Volumes and persistence

Docker volumes persist data across restarts:

| Volume | Service | Contents |
|--------|---------|----------|
| `grafana_data` | Grafana | Dashboards, datasources, users |
| `prometheus_data` | Prometheus | Metrics TSDB |
| `loki_data` | Loki | Log chunks and index |

### Full reset

```sh
# Delete everything and start fresh
docker compose down -v
docker compose up -d
```

## Extending the stack

### Adding a service to monitor

1. Modify `.docker/conf.alloy`:
```alloy
prometheus.scrape "my_service" {
  targets = [{
    __address__ = "my-service:8080",
  }]
  forward_to = [prometheus.remote_write.prom.receiver]
  job_name   = "my-service"
}
```

2. Restart Alloy:
```sh
docker compose restart alloy
```

### Adding file log collection

```alloy
local.file_match "app_logs" {
  path_targets = [{"__path__" = "/var/log/app/*.log"}]
}

loki.source.file "app_logs" {
  targets    = local.file_match.app_logs.targets
  forward_to = [loki.write.loki.receiver]
}
```
