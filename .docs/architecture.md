# Architecture documentation

## Data Pipeline: Grafana to Azure Blob Storage

The `push_to_blob.py` script is the main data pipeline responsible for collecting observability metrics from Grafana and persisting them as daily chunks in Azure Blob Storage for long-term storage and later use by ML models.

### Overview

```
configs/queries.yaml        Grafana (Prometheus + Loki)        Azure Blob Storage
 ┌──────────────┐           ┌──────────────────────┐          ┌──────────────────────────────┐
 │  PromQL &    │──parse──▶ │  /api/ds/query        │──upload─▶│  container/                  │
 │  LogQL       │           │  (24h time window)    │          │   chunk_obs-dataset_YYYYMMDD  │
 │  queries     │           └──────────────────────┘          │   .parquet                   │
 └──────────────┘                     │                        └──────────────────────────────┘
                                      ▼
                              Polars DataFrames
                              (filter, process,
                               merge, parquet)
```

### Step-by-step flow

#### 1. Query parsing

Queries are defined in `configs/queries.yaml` and organized by datasource type (`prometheus`, `loki`) and datasource name:

```yaml
prometheus:
  Mimir:
    - id: alloy_queue_length
      query: "avg_over_time(scrape_duration_seconds{...}[1m])"

loki:
  Loki:
    - id: loki_request_rate
      query: "count_over_time({service_name=\"alloy\"} |= \"info\" [1m])"
```

Each query has a unique `id` that becomes the column name in the final dataset.

#### 2. Data retrieval from Grafana (24h window)

The script calculates a **24-hour time window** ending at the current time:

```
to_time   = now
from_time = now - 86400s (1 day)
```

The `DEFAULT_TIME_WINDOW` is defined as `Time.DAY.value` (86400 seconds) in `src/data/grafana.py`.

All queries (Prometheus and Loki) are executed **in parallel** via `asyncio.gather()` against Grafana's unified query API (`/api/ds/query`). For each datasource name referenced in the config, the script first resolves its UID via the Grafana API, then fires all queries concurrently.

A retry strategy (3 retries with exponential backoff) handles transient API failures (429, 5xx).

#### 3. Conversion and filtering

Each query result is converted into a Polars DataFrame with two columns: `timestamp` (Int64) and `value` (Float64). During conversion, the following rows are dropped:

- Rows with `NaN` values
- Rows with negative timestamps (`timestamp <= 0`)

Empty query results are skipped entirely.

#### 4. Processing

DataFrames are passed through the `AlloyProcessor` which applies domain-specific sanitization and processing logic.

#### 5. Merge into a single wide DataFrame

All per-query DataFrames are merged into a single wide-format DataFrame using `join_asof` on the `timestamp` column:

- **Strategy**: `nearest` — matches the closest timestamp
- **Tolerance**: `15,000ms` (15 seconds) — accounts for timing misalignment between Prometheus and Loki scrape intervals

The resulting DataFrame has one `timestamp` column and one column per query id (e.g. `alloy_queue_length`, `loki_request_rate`). Timestamps outside the tolerance window produce `null` values.

The merged DataFrame is then sorted by timestamp and written locally as a Parquet file (Snappy compression) at `output/output.parquet`.

#### 6. Upload to Azure Blob Storage

The local Parquet file is uploaded to Azure Blob Storage with a **date-based naming convention**:

```
chunk_obs-dataset_YYYYMMDD.parquet
```

| Segment | Value | Source |
|---------|-------|--------|
| `chunk_` | Fixed prefix | `AzureInterface.file_prefix` |
| `obs-dataset_` | Fixed identifier | Hardcoded in `AzureInterface.upload()` |
| `YYYYMMDD` | Current date (e.g. `20260208`) | `time.strftime("%Y%m%d")` |
| `.parquet` | File extension | — |

The upload overwrites any existing blob with the same name (`overwrite=True`), so re-running the pipeline on the same day replaces the previous chunk.

#### 7. Cleanup

After a successful upload, the local `output/output.parquet` file is deleted.

### Execution modes

| Mode | Flag | Behavior |
|------|------|----------|
| Interactive (default) | — | Displays a preview of the merged DataFrame + chart, asks for user confirmation before uploading |
| Force | `--force` | Skips visualization and confirmation, pushes directly — intended for CI/CD |

### Required environment variables

| Variable | Description |
|----------|-------------|
| `GRAFANA_URL` | Grafana instance URL |
| `GRAFANA_SA_TOKEN` | Grafana service account token |
| `AZURE_STORAGE_CONNECTION_STRING` | Azure Storage connection string |
| `AZURE_STORAGE_CONTAINER_NAME` | Target container name |

### Blob Storage structure

Over time, the container accumulates one chunk per day:

```
<container>/
  chunk_obs-dataset_20260201.parquet
  chunk_obs-dataset_20260202.parquet
  chunk_obs-dataset_20260203.parquet
  ...
  chunk_obs-dataset_20260208.parquet
```

Each chunk contains the full 24h of observability data for its corresponding day. These chunks are then available for downstream consumption by ML training pipelines.
