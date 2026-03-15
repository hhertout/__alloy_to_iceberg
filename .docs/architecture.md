# Architecture documentation

## Overview

The project is composed of four pipelines:

```
configs/config.yaml              Grafana (Prometheus + Loki)
 ┌──────────────────┐            ┌──────────────────────┐
 │  producer        │──scrape──▶ │  /api/ds/query       │
 │  queries         │            │  (last N minutes)    │
 └──────────────────┘            └──────────┬───────────┘
                                            │ OTLP JSON
                                            ▼
                                   ┌─────────────────┐
                                   │  Kafka topic    │
                                   │  (metrics/logs) │
                                   └────────┬────────┘
                                            │ consume
                                            ▼
                                 ┌─────────────────────┐      ┌──────────────────────────┐
                                 │  Integration        │      │  Iceberg (ADLS / S3)     │
                                 │  pipeline           │─────▶│  obs.otlp_metric         │
                                 │  (batch + flush)    │      │  obs.otlp_log            │
                                 └─────────────────────┘      └──────────────────────────┘
                                                                          │
                                                                    DuckDB scan
                                                                          │
                                                                          ▼
                              Azure Blob Storage             ┌────────────────────────┐
                               ┌──────────────┐             │  Training pipeline     │
                               │  models/     │◀── save ────│  (feature eng. + fit)  │
                               │   model.pt   │             └────────────────────────┘
                               └──────┬───────┘
                                      │ load
                                      ▼
                             ┌──────────────────┐     Grafana (live)      ┌──────────────┐
                             │  Inference       │◀── /api/ds/query ───────│  Prometheus  │
                             │  pipeline        │──── remote write ──────▶│  (TSDB)      │
                             └──────────────────┘                         └──────────────┘
```

### Pipelines

| Script | Role |
|--------|------|
| `metrics_producer.py` | Scrapes Grafana at a fixed interval, converts responses to OTLP JSON, publishes to Kafka |
| `integration_pipeline.py` | Consumes Kafka, deserializes OTLP protobuf, batches rows, writes to Iceberg |
| `train.py` | Reads from Iceberg via DuckDB, runs feature engineering, trains models (LSTM, XGBoost, RF, Prophet) |
| `predict.py` | Loads a trained model, fetches live Grafana data, writes predictions back to Prometheus via remote write |

---

## Pipeline 1: Metrics producer (`metrics_producer.py`)

Periodically scrapes Grafana datasources and publishes OTLP-encoded metrics to Kafka.

### Step-by-step flow

The following steps describe how the metrics producer works.

#### 1. Query configuration

Queries are defined in `configs/config.yaml` under `integration.producer.queries`, organized by datasource type and name. Each entry declares a `resource_attributes` map that tags the resulting OTLP data points:

```yaml
integration:
  producer:
    scrape_interval_min: 1
    queries:
      prometheus:
        Mimir:
          - id: avg_scrape_duration_seconds
            query: "avg_over_time(scrape_duration_seconds{...}[1m])"
            resource_attributes:
              service.name: integrations
              service.instance.id: alloy-jhfs786sbh9
```

#### 2. Grafana query

For each configured query, the producer calls Grafana's `/api/ds/query` endpoint over the last `scrape_interval_min` minutes, resolving datasource UIDs on first use.

#### 3. OTLP conversion and Kafka publish

Grafana responses are converted to `ExportMetricsServiceRequest` protobuf messages via `utils/grafana_to_otlp.py` and serialized to JSON before being published to the `metrics` Kafka topic.

---

## Pipeline 2: Integration pipeline (`integration_pipeline.py`)

Consumes OTLP messages from Kafka and writes them to an Iceberg data lake in batches.

### Step-by-step flow

The following steps describe how the integration pipeline works.

#### 1. Kafka consumption

The pipeline subscribes to the `metrics` Kafka topic with `enable.auto.commit: false`, polling in a tight loop. Graceful shutdown handles `SIGTERM` and `SIGINT`, flushing the current batch before exit.

#### 2. OTLP deserialization

Each Kafka message is deserialized by `OtlpJsonParser` into an `ExportMetricsServiceRequest` protobuf, then flattened by `IntegrationPipelineProcessor` into a Polars DataFrame with a stable Iceberg-compatible schema:

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `TimestampTZ` | From `time_unix_nano`, partition key |
| `__name__` | `String` | Metric name |
| `value` | `Double` | Numeric value |
| `service_name` | `String` | Promoted from resource attributes |
| `resource_attributes` | `List<Struct>` | Full resource attributes |
| `attributes` | `List<Struct>` | Per-datapoint attributes |

#### 3. Batching

Rows accumulate in a `Batch` object (list of DataFrames). When the batch reaches `integration.batch_size` MB, it is flushed to Iceberg and the Kafka offset is committed synchronously.

#### 4. Iceberg write

Batches are written via PyIceberg's `table.append()` (Arrow). Tables are partitioned by day on `timestamp` for efficient time-range scans. ZSTD compression is applied at the Parquet level.

### Iceberg table structure

```
<warehouse>/obs/
  otlp_metric/      ← partitioned by timestamp_day
  otlp_log/         ← partitioned by timestamp_day (schema TBD)
```

### Schema migrations

The `MetricsMigration` class in `src/integration/migrations/migrator.py` runs on every cold start. Migrations are versioned methods (`__v01`, `__v02`, ...) executed in order via `update_schema()`.

---

## Pipeline 3: Model training (`train.py`)

Reads accumulated data from Iceberg, engineers features, and trains one or more models.

### Step-by-step flow

The following steps describe how the training pipeline works.

#### 1. Data retrieval from Iceberg

`BlobRepository.get_data_for_training()` uses DuckDB to scan the Iceberg `otlp_metric` table and pivot the long-format rows into a wide-format time series suitable for feature engineering.

#### 2. Feature engineering

The feature engineering layer uses a **versioned inheritance pattern**:

```
src/features/
  base.py   ← abstract base class (FeaturesEngineering)
  v1.py     ← concrete version (FeaturesEngineeringV1)
```

**Base class** (`base.py`):
- **Column names:** Loads column names from `configs/queries.yaml` via `get_queries_id()`, returning a `SimpleNamespace` for attribute access.
- **Window sizes:** Defines shared window sizes as integer-based Polars durations (in ms).
- **Pipeline execution:** Exposes `generate_ml_features(df)` and `generate_torch_features(df)` which apply pipes sequentially.

**Version classes** (for example `v1.py`):
- Implement `_get_ml_pipes()` and `_get_torch_pipes()` to define their pipeline.
- Version-specific features are private methods (`__` prefix, name-mangled to the version class).

**Adding a new version**:

1. Create `src/features/v2.py` inheriting from `FeaturesEngineering`.
2. Implement `_get_ml_pipes()` and `_get_torch_pipes()`.
3. Switch the import in `scripts/train.py`.

#### 3. Model training

The pipeline supports four model types, each enabled via `configs/config.yaml`:

| Model | Module | Config key |
|-------|--------|------------|
| LSTM (PyTorch) | `src/pytorch/v1.py` | `models.pytorch` |
| Random Forest | `src/sklearn/v1.py` | `models.random_forest` |
| XGBoost | `src/sklearn/v1.py` | `models.xgboost` |
| Prophet | `src/prophet/v1.py` | `models.prophet` |

#### 4. Model persistence

Trained model artifacts are uploaded to the `models/` folder in Azure Blob Storage, making them available for the inference pipeline.

---

## Pipeline 4: Inference (`predict.py`)

Retrieves the latest trained model and live metrics, runs predictions, and writes results to a TSDB.

### Step-by-step flow

The following steps describe how the inference pipeline works.

#### 1. Retrieve model

The script downloads the latest model artifact from the `models/` folder in Azure Blob Storage.

#### 2. Retrieve live data

The script fetches current observability metrics from Grafana using the same query definitions as the metrics producer.

#### 3. Predict and write to TSDB

The model runs inference on live data and pushes predicted values to Prometheus via remote write, making them available alongside actual metrics in Grafana dashboards.

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
