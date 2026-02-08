# Architecture documentation

## Overview

The project is composed of three pipelines, each corresponding to a script:

### 1. Data collection (`push_to_blob.py`)

```
configs/queries.yaml        Grafana (Prometheus + Loki)              Azure Blob Storage
 ┌──────────────┐           ┌──────────────────────┐          ┌─────────────────────────────────────┐
 │  PromQL &    │──parse──▶ │  /api/ds/query       │──upload─▶│  container/chunks/                  │
 │  LogQL       │           │  (previous day)      │          │   chunk_dataframe_YYYYMMDD.parquet  │
 │  + agg       │           └──────────────────────┘          └─────────────────────────────────────┘
 └──────────────┘                     │
                                      ▼
                              Polars DataFrames
                              (merge, resample,
                               process, parquet)
```

### 2. Model training (`generate_model.py`)

```
Azure Blob Storage                                                    Azure Blob Storage
 ┌──────────────────────┐                                              ┌──────────────────┐
 │  container/chunks/   │──download──▶ Polars DataFrame ──▶ Feature ──▶│  container/      │
 │  (last N days)       │              (concat chunks)      eng.       │  models/         │
 └──────────────────────┘                                    │         │   model.pt       │
                                                             ▼         └──────────────────┘
                                                       PyTorch train
                                                         & save
```

### 3. Inference (`predict.py`)

```
Azure Blob Storage        Grafana (live data)                        TSDB
 ┌──────────────────┐     ┌──────────────────────┐          ┌──────────────┐
 │  container/      │     │  /api/ds/query       │          │  Prometheus  │
 │  models/         │     │  (current window)    │          │  (remote     │
 │   model.pt       │     └──────────┬───────────┘          │   write)     │
 └────────┬─────────┘                │                      └──────────────┘
          │                          │                              ▲
          ▼                          ▼                              │
     Load model              Live metrics                           │
          │                          │                              │
          └──────────┬───────────────┘                              │
                     ▼                                              │
                  Predict ──────────────────────────────────────────┘
```

---

## Pipeline 1: Data collection (`push_to_blob.py`)

Collects observability metrics from Grafana and persists them as daily Parquet chunks in Azure Blob Storage.

### Step-by-step flow

#### 1. Query parsing

Queries are defined in `configs/queries.yaml` and organized by datasource type (`prometheus`, `loki`) and datasource name. Each query specifies an aggregation strategy (`agg`) used during resampling:

```yaml
prometheus:
  Mimir:
    - id: alloy_queue_length
      agg: mean
      query: "sum(avg_over_time(scrape_duration_seconds{...}[1m]))"

loki:
  Loki:
    - id: loki_request_rate
      agg: mean
      query: "count_over_time({service_name=\"alloy\"} |= \"info\" [1m])"
```

Each query has a unique `id` that becomes the column name in the final dataset. The `agg` field (defaults to `mean` if omitted) controls how values are aggregated during the resampling step.

#### 2. Data retrieval from Grafana (previous day)

The script retrieves data for **the previous full day** using `get_previous_day_range()`:

```
from_time = yesterday 00:00:00 UTC
to_time   = yesterday 23:59:59 UTC
```

This ensures each chunk covers a clean, complete calendar day regardless of when the pipeline runs.

All queries (Prometheus and Loki) are executed **in parallel** via `asyncio.gather()` against Grafana's unified query API (`/api/ds/query`). For each datasource name referenced in the config, the script first resolves its UID via the Grafana API, then fires all queries concurrently.

A retry strategy (3 retries with exponential backoff) handles transient API failures (429, 5xx).

#### 3. Merge and resample

All per-query time series are merged into a single wide-format DataFrame in `src/processing/merge_dataframes.py`:

1. **Unified timeline**: all unique timestamps from every source are collected into a single sorted column.
2. **Left join**: each metric is joined onto this timeline using `join` (exact match), producing `null` where a source has no value for a given timestamp.
3. **Resampling**: the merged DataFrame is resampled via `group_by_dynamic` at a regular interval of `DEFAULT_AGG_INTERVAL_MS` (60,000ms = 1 minute). Each column is aggregated using the strategy declared in the query config (`mean`, `sum`, `min`, `max`, `first`, `last`).

The resulting DataFrame has one `timestamp` column and one column per query id.

#### 4. Processing and validation

The `Processor` class (`src/processing/data_processing.py`) is applied on the merged DataFrame:

- Removes rows with `NaN` values
- Fills `null` values with `0.0` for known metric columns

After processing, the pipeline **validates** that no `null` or `NaN` values remain. If any are found, the pipeline aborts with an error to prevent pushing corrupt data.

The clean DataFrame is then sorted by timestamp and written locally as a Parquet file (Snappy compression) at `output/output.parquet`.

#### 5. Upload to Azure Blob Storage

The local Parquet file is uploaded to Azure Blob Storage with a **date-based naming convention** inside a `chunks/` folder:

```
chunks/chunk_dataframe_YYYYMMDD.parquet
```

| Segment | Value | Source |
|---------|-------|--------|
| `chunks/` | Folder | `AzureInterface.chunk_folder` |
| `chunk` | Fixed prefix | `AzureInterface.file_prefix` |
| `dataframe` | Fixed identifier | `AzureInterface.file_identifier` |
| `YYYYMMDD` | Current date (e.g. `20260208`) | `time.strftime("%Y%m%d")` |
| `.parquet` | File extension | `AzureInterface.file_extension` |

The upload overwrites any existing blob with the same name (`overwrite=True`), so re-running the pipeline on the same day replaces the previous chunk.

#### 6. Cleanup

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
  chunks/
    chunk_dataframe_20260201.parquet
    chunk_dataframe_20260202.parquet
    chunk_dataframe_20260203.parquet
    ...
    chunk_dataframe_20260208.parquet
  models/
    ...
```

Each chunk contains one full calendar day of resampled observability data.

---

## Pipeline 2: Model training (`generate_model.py`)

Retrieves accumulated data chunks from Azure Blob Storage, prepares a training dataset, trains a PyTorch model, and pushes the resulting model back to blob storage.

### Step-by-step flow

#### 1. Retrieve chunks from Azure Blob Storage

The script downloads the last `TRAINING_TIMEWINDOW_DAYS` days of chunks (default: 3) from the `chunks/` folder. Each chunk is fetched by date using `AzureInterface.get_chunk()`. Missing chunks (e.g. pipeline didn't run that day) are logged and skipped.

#### 2. Merge into a training DataFrame

All downloaded Parquet chunks are read and concatenated into a single Polars DataFrame, forming a multi-day continuous time series.

#### 3. Feature engineering

Features are derived from the raw merged dataset to prepare the input for the model (TBD).

#### 4. Model training

A PyTorch model is trained on the prepared features (TBD).

#### 5. Push model to Azure Blob Storage

The trained model artifact is uploaded to the `models/` folder in Azure Blob Storage, making it available for the prediction pipeline.

---

## Pipeline 3: Inference (`predict.py`)

Retrieves the latest trained model and live data, runs predictions, and writes the results to a time-series database.

### Step-by-step flow

#### 1. Retrieve model from Azure Blob Storage

The latest model artifact is downloaded from the `models/` folder in Azure Blob Storage.

#### 2. Retrieve live data

Current observability metrics are fetched from Grafana using the same query definitions as the data collection pipeline.

#### 3. Predict

The model runs inference on the live data to produce forecasted metric values.

#### 4. Write predictions to TSDB

Predicted values are pushed to a time-series database (e.g. Prometheus via remote write), making them available in Grafana dashboards alongside actual metrics for comparison and alerting.
