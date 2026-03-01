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

The following steps describe how the data collection pipeline works.

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

The script executes all queries (Prometheus and Loki) **in parallel** via `asyncio.gather()` against Grafana's unified query API (`/api/ds/query`). For each datasource name referenced in the config, it first resolves the UID via the Grafana API, then fires all queries concurrently.

A retry strategy (3 retries with exponential backoff) handles transient API failures (429, 5xx).

#### 3. Merge and resample

All per-query time series are merged into a single wide-format DataFrame in `src/processing/merge_dataframes.py`:

1. **Unified timeline**: all unique timestamps from every source are collected into a single sorted column.
2. **Left join**: each metric is joined onto this timeline using `join` (exact match), producing `null` where a source has no value for a given timestamp.
3. **Resampling**: the merged DataFrame is resampled via `group_by_dynamic` at a regular interval of `DEFAULT_AGG_INTERVAL_MS` (60,000ms = 1 minute). Each column is aggregated using the strategy declared in the query config (`mean`, `sum`, `min`, `max`, `first`, `last`).

The resulting DataFrame has one `timestamp` column and one column per query id.

#### 4. Processing and validation

The `Processor` class (`src/processing/data_processing.py`) applies the following transformations on the merged DataFrame:

- **NaN removal:** Drops rows that contain `NaN` values.
- **Null filling:** Replaces `null` values with `0.0` for known metric columns.

After processing, the pipeline **validates** that no `null` or `NaN` values remain. If it finds any, the pipeline aborts with an error to prevent pushing corrupt data.

The pipeline then sorts the clean DataFrame by timestamp and writes it locally as a Parquet file (Snappy compression) at `output/output.parquet`.

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

The pipeline supports two execution modes:

| Mode | Flag | Behavior |
|------|------|----------|
| Interactive (default) | — | Displays a preview of the merged DataFrame + chart, asks for user confirmation before uploading |
| Force | `--force` | Skips visualization and confirmation, pushes directly — intended for CI/CD |

### Required environment variables

You need the following environment variables to run the pipeline:

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

This pipeline retrieves accumulated data chunks from Azure Blob Storage, prepares a training dataset, trains a PyTorch model, and pushes the resulting model back to blob storage.

### Step-by-step flow

The following steps describe how the model training pipeline works.

#### 1. Retrieve chunks from Azure Blob Storage

The script downloads the last `TRAINING_TIMEWINDOW_DAYS` days of chunks (default: 3) from the `chunks/` folder. It fetches each chunk by date using `AzureInterface.get_chunk()`. It logs and skips missing chunks (for example, if the pipeline didn't run that day).

#### 2. Merge into a training DataFrame

The script reads and concatenates all downloaded Parquet chunks into a single Polars DataFrame, forming a multi-day continuous time series.

#### 3. Feature engineering

The pipeline derives features from the raw merged dataset to prepare the input for the model.

The feature engineering layer uses a **versioned inheritance pattern**:

```
src/features/
  base.py   ← abstract base class (FeaturesEngineering)
  v1.py     ← concrete version (FeaturesEngineeringV1)
  v2.py     ← future versions...
```

**Base class** (`base.py`):
- **Column names:** Loads column names from `configs/queries.yaml` via `get_queries_id()`, which returns a `SimpleNamespace` for attribute access. Typos raise `AttributeError`.
- **Window sizes:** Defines shared window sizes (`window_size_5m`, `window_size_10m`) as integer-based Polars durations (in ms).
- **Pipeline execution:** Exposes `generate_features(df)` which applies all pipes from `_get_pipes()` sequentially.
- **Common features:** Hosts features shared across versions (single `_` prefix for subclass access).
- **Telemetry:** Reports the number of generated features via OTel gauge (`ml.features.number`).

**Version classes** (for example `v1.py`):
- **Inheritance:** Inherit from `FeaturesEngineering` and implement `_get_pipes()` to define their pipeline.
- **Private methods:** Define version-specific features as private methods (`__` prefix, name-mangled to the version class).
- **Pipe signature:** Each pipe is a function `(DataFrame) -> DataFrame`, applied via `df.pipe()`.

**V1 features**:

| Feature | Method | Description |
|---------|--------|-------------|
| `alloy_queue_length_mean` | `__alloy_rolling_mean` | Rolling mean over 5min window |
| `alloy_queue_length_p50` | `__alloy_rolling_p50` | Rolling median (p50) over 5min window |

**Adding a new version**:

1. Create `src/features/v2.py` inheriting from `FeaturesEngineering`
2. Implement `_get_pipes()` with the desired feature set (mix of common `_` methods from base and private `__` methods)
3. Switch the import in `scripts/generate_model.py`

This allows comparing model performance across feature sets without destroying previous work.

#### 4. Model training

The pipeline trains a PyTorch model on the prepared features (TBD).

#### 5. Push model to Azure Blob Storage

The script uploads the trained model artifact to the `models/` folder in Azure Blob Storage, making it available for the prediction pipeline.

---

## Pipeline 3: Inference (`predict.py`)

This pipeline retrieves the latest trained model and live data, runs predictions, and writes the results to a time-series database.

### Step-by-step flow

The following steps describe how the inference pipeline works.

#### 1. Retrieve model from Azure Blob Storage

The script downloads the latest model artifact from the `models/` folder in Azure Blob Storage.

#### 2. Retrieve live data

The script fetches current observability metrics from Grafana using the same query definitions as the data collection pipeline.

#### 3. Predict

The model runs inference on the live data to produce forecasted metric values.

#### 4. Write predictions to TSDB

The script pushes predicted values to a time-series database (for example, Prometheus via remote write), making them available in Grafana dashboards alongside actual metrics for comparison and alerting.

---

## Storage estimation

This section estimates the storage footprint and cost of the Iceberg data lake over time.

### Reference measurement

A representative Parquet file (ZSTD compression) with 20,000 rows and 11 columns weighs **43 KB**, giving a compressed density of roughly **2.15 bytes per row**. This is typical for metrics data: Parquet's dictionary encoding collapses repeated strings (metric names, label values) very efficiently before ZSTD compresses further.

### Model

The estimation uses the following parameters:

- **Metrics scraped**: 50
- **Scrape interval**: 30 seconds → 2,880 scrapes/day → 86,400 scrapes/month
- **Series per metric**: variable (see scenarios below). Each series corresponds to a unique label combination (for example, `{method="GET", status="200"}` and `{method="POST", status="500"}` are two series for the same metric).

Each scrape produces one row per series per metric. The formula is:

```
rows/month = metrics × series/metric × scrapes/month
           = 50 × series/metric × 86,400
```

### Scenarios

| Scenario | Series/metric | Rows/scrape | Rows/month | Storage/month | Storage/year |
|----------|--------------|-------------|------------|---------------|--------------|
| Small    | 5            | 250         | 21.6 M     | ~46 MB        | ~560 MB      |
| Medium   | 20           | 1,000       | 86.4 M     | ~186 MB       | ~2.2 GB      |
| Large    | 50           | 2,500       | 216 M      | ~465 MB       | ~5.6 GB      |

Storage per month = rows/month × 2.15 bytes.
Storage per year is cumulative (data accumulates, not overwritten).

### Azure Blob Storage cost (LRS, West Europe, Hot tier)

| Component             | Price                     |
|-----------------------|---------------------------|
| Storage               | ~$0.018 / GB / month      |
| Write operations      | ~$0.053 / 10k ops         |
| Read operations       | ~$0.0045 / 10k ops        |

Estimated monthly cost at end of year (cumulative data):

| Scenario | Storage at month 12 | Storage cost/month |
|----------|--------------------|--------------------|
| Small    | ~560 MB            | ~$0.01             |
| Medium   | ~2.2 GB            | ~$0.04             |
| Large    | ~5.6 GB            | ~$0.10             |

Storage cost is negligible. The dominant cost at scale is **compute** (integration pipeline, training jobs) and **operations** (Iceberg metadata writes on each batch flush), not raw storage.
