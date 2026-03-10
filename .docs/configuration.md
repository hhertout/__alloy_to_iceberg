# Configuration parameters

This document describes every parameter available in `configs/config.yaml`.

The configuration file uses YAML. Many parameters accept an environment variable reference as their value using the `$ENV_VAR_NAME` syntax. When a parameter is set this way, the application resolves it at startup from the process environment. If both the config file and an environment variable are defined, the config file value takes precedence unless it's a `$` reference, in which case the environment variable is resolved.

## `log`

Controls application logging.

```yaml
log:
  # Logging level.
  # Accepted values: debug, info, warn, error.
  # Env: LOG_LEVEL
  [level: <string> | default = "info"]
```

## `grafana`

Configures the connection to the Grafana instance used by the producer to scrape metrics and logs.

```yaml
grafana:
  # URL of the Grafana instance.
  # Env: GRAFANA_URL
  [url: <string>]

  # Grafana service account token used to authenticate API requests.
  # Env: GRAFANA_API_KEY
  [api_key: <string>]
```

## `storage`

Configures the backend used to persist Parquet chunks and model artifacts. You must define exactly one backend: either `azure` or `s3`.

### `storage.azure`

Uses Azure Blob Storage as the persistence backend.

```yaml
storage:
  azure:
    # Azure Storage account name.
    # Env: AZURE_STORAGE_ACCOUNT_NAME
    [account_name: <string>]

    # Name of the target container.
    # Env: AZURE_STORAGE_CONTAINER_NAME
    [container_name: <string>]

    # Full Azure Storage connection string.
    # Env: AZURE_STORAGE_CONNECTION_STRING
    [connection_string: <string>]

    # Prefix used when naming blob files.
    [file_prefix: <string> | default = "chunk"]

    # Identifier segment used when naming blob files.
    [file_identifier: <string> | default = "dataframe"]

    # Folder inside the container where daily data chunks are stored.
    [chunk_folder: <string> | default = "chunks"]

    # Folder inside the container where trained model artifacts are stored.
    [models_folder: <string> | default = "models"]
```

### `storage.s3`

Uses Amazon S3 (or any S3-compatible endpoint) as the persistence backend.

```yaml
storage:
  s3:
    # S3 bucket name.
    # Env: AWS_S3_BUCKET_NAME
    [bucket_name: <string>]

    # AWS region.
    # Env: AWS_S3_REGION | AWS_DEFAULT_REGION
    [region_name: <string>]

    # Custom endpoint URL for S3-compatible storage (e.g., MinIO).
    # Env: AWS_S3_ENDPOINT_URL
    [endpoint_url: <string>]

    # AWS access key ID.
    # Env: AWS_ACCESS_KEY_ID
    [aws_access_key_id: <string>]

    # AWS secret access key.
    # Env: AWS_SECRET_ACCESS_KEY
    [aws_secret_access_key: <string>]

    # AWS session token for temporary credentials.
    # Env: AWS_SESSION_TOKEN
    [aws_session_token: <string>]

    # Prefix used when naming blob files.
    [file_prefix: <string> | default = "chunk"]

    # Identifier segment used when naming blob files.
    [file_identifier: <string> | default = "dataframe"]

    # Folder inside the bucket where daily data chunks are stored.
    [chunk_folder: <string> | default = "chunks"]

    # Folder inside the bucket where trained model artifacts are stored.
    [models_folder: <string> | default = "models"]
```

## `integration`

Configures the integration pipeline, which covers the producer (Grafana scraping), the Kafka transport layer, and the consumer (Iceberg writes).

```yaml
integration:
  # Number of rows accumulated in memory before flushing a batch to Iceberg.
  [batch_size: <int> | default = 1000]
```

### `integration.producer`

Configures how the producer scrapes data from Grafana datasources.

```yaml
integration:
  producer:
    # How often the producer scrapes Grafana datasources, in minutes.
    [scrape_interval_min: <int> | default = 1]
```

#### `integration.producer.queries`

Defines the queries the producer runs against each Grafana datasource. Queries are grouped by datasource type (`prometheus`, `loki`) and then by datasource name as it appears in Grafana.

Each query entry accepts the following fields:

```yaml
integration:
  producer:
    queries:
      prometheus:
        <DATASOURCE_NAME>:
          - # Unique identifier for this query. Becomes the column name in storage.
            id: <string>

            # PromQL expression to execute. Must return numeric values.
            query: <string>

            # (optional) OTel resource attributes attached to each data point.
            resource_attributes:
              [<key>: <string>]

      loki:
        <DATASOURCE_NAME>:
          - # Unique identifier for this query. Becomes the column name in storage.
            id: <string>

            # LogQL expression to execute. Must return numeric values (e.g., count_over_time).
            query: <string>

            # (optional) OTel resource attributes attached to each data point.
            resource_attributes:
              [<key>: <string>]
```

### `integration.kafka`

Configures the Kafka broker and topics used to transport OTel data between the producer and the consumer.

```yaml
integration:
  kafka:
    # Address of the Kafka broker (e.g., localhost:9092).
    # Env: KAFKA_BROKER
    [broker: <string>]

    topic:
      # Topic used to transport metric data points.
      # Env: KAFKA_TOPIC_METRICS | KAFKA_TOPIC
      [metrics: <string>]

      # Topic used to transport log data points.
      # Env: KAFKA_TOPIC_LOGS
      [logs: <string>]

    # Consumer group ID used by the consumer workload.
    # Env: KAFKA_GROUP_ID
    [group_id: <string>]
```

### `integration.iceberg`

Configures the Iceberg catalog and warehouse used by the consumer to persist processed data. You must define exactly one catalog backend: `postgres`, `polaris`, or `unity`.

```yaml
integration:
  iceberg:
    # Name of the Iceberg catalog.
    [catalog_name: <string>]

    # Name of the database inside the catalog.
    [database_name: <string>]

    # Namespace used when creating or querying Iceberg tables.
    [namespace: <string>]

    # (optional) Table name override.
    [table_name: <string>]

    # Path to the warehouse inside the storage backend.
    [warehouse_path: <string> | default = "warehouse"]
```

#### `integration.iceberg.postgres`

Uses a PostgreSQL database as the Iceberg catalog backend.

```yaml
integration:
  iceberg:
    postgres:
      # PostgreSQL connection string.
      # Env: POSTGRESQL_CONNECTION_STRING
      [connection_string: <string>]

      # Whether to enforce SSL on the PostgreSQL connection.
      [ssl_enabled: <boolean> | default = false]
```

#### `integration.iceberg.polaris`

Uses an Apache Polaris REST catalog as the Iceberg catalog backend.

```yaml
integration:
  iceberg:
    polaris:
      # URL of the Polaris catalog REST API.
      # Env: POLARIS_URL
      [url: <string>]

      # Authentication token for the Polaris API.
      # Env: POLARIS_TOKEN
      [token: <string>]
```

#### `integration.iceberg.unity`

Uses a Databricks Unity Catalog as the Iceberg catalog backend via the REST API. Unity Catalog manages storage locations internally, so the `warehouse_path` setting is ignored when this backend is active.

```yaml
integration:
  iceberg:
    unity:
      # URL of the Databricks workspace (e.g. https://<workspace>.cloud.databricks.com).
      # Env: DATABRICKS_HOST
      [workspace_url: <string>]

      # Databricks personal access token or OAuth M2M token.
      # Env: DATABRICKS_TOKEN
      [token: <string>]

      # (optional) SQL warehouse ID used for write operations.
      # Env: DATABRICKS_WAREHOUSE_ID
      [warehouse_id: <string>]
```

### `integration.metrics`

Defines which metrics the consumer keeps when reading from Kafka. Metrics not matching any entry in `include` are dropped.

```yaml
integration:
  metrics:
    include:
      - # Name of the metric to include.
        name: <string>

        # (optional) OTel resource attribute filters. Only data points matching
        # all specified key-value pairs are kept. Supports regex values.
        resource_attributes:
          [<key>: <string>]

        # (optional) OTel attribute filters. Only data points matching
        # all specified key-value pairs are kept. Supports regex values.
        attributes:
          [<key>: <string>]
```

### `integration.logs`

Defines which log entries the consumer keeps when reading from Kafka. Log entries not matching any rule in `include` are dropped.

```yaml
integration:
  logs:
    include:
      - # (optional) Service name filter. Matches the OTel resource attribute service.name.
        [service_name: <string>]

        # (optional) Log level filter (e.g., info, warn, error).
        [level: <string>]

        # (optional) Substring or regex matched against the log body.
        [contains: <string>]
```

## `limits`

Controls the data window and split ratios used during model training.

```yaml
limits:
  # Number of additional days added to the training window, counted backwards from today.
  [offset_days: <int> | default = 0]

  # Number of days of historical data to include in the training dataset.
  [training_window_days: <int> | default = 90]

  # Proportion of the dataset reserved for the test split.
  # Accepted range: 0.0 to 1.0.
  [training_test_size: <float> | default = 0.15]

  # Proportion of the dataset reserved for the validation split.
  # Accepted range: 0.0 to 1.0.
  [training_val_size: <float> | default = 0.15]

  # Name of the target column in the training dataset.
  [target_column_name: <string> | default = "target"]
```

## `models`

Enables and configures the models available for training. Each model is opt-in via its `enabled` flag.

### `models.random_forest`

Configures the scikit-learn Random Forest model.

```yaml
models:
  random_forest:
    [enabled: <boolean> | default = false]

    # Number of trees in the forest.
    [n_estimators: <int> | default = 100]

    # Maximum depth of each tree.
    [max_depth: <int> | default = 10]

    # Minimum number of samples required to split an internal node.
    [min_samples_split: <int> | default = 10]

    # Random seed for reproducibility.
    [random_state: <int> | default = 42]

    # Number of parallel jobs. Set to -1 to use all available CPUs.
    [n_jobs: <int> | default = -1]

    [verbose: <int> | default = 0]
```

### `models.xgboost`

Configures the XGBoost gradient boosting model.

```yaml
models:
  xgboost:
    [enabled: <boolean> | default = false]

    # Number of boosting rounds.
    [n_estimators: <int> | default = 300]

    # Maximum tree depth.
    [max_depth: <int> | default = 6]

    # Step size shrinkage applied after each boosting round.
    [learning_rate: <float> | default = 0.05]

    # Fraction of training samples used per tree.
    [subsample: <float> | default = 0.9]

    # Fraction of features used per tree.
    [colsample_bytree: <float> | default = 0.9]

    # Minimum sum of instance weights in a leaf node.
    [min_child_weight: <float> | default = 1.0]

    # Minimum loss reduction required to make a further partition.
    [gamma: <float> | default = 0.0]

    # L1 regularization term on weights.
    [reg_alpha: <float> | default = 0.0]

    # L2 regularization term on weights.
    [reg_lambda: <float> | default = 1.0]

    # Random seed for reproducibility.
    [random_state: <int> | default = 42]

    # Number of parallel jobs. Set to -1 to use all available CPUs.
    [n_jobs: <int> | default = -1]

    # Verbosity level (0 = silent).
    [verbosity: <int> | default = 0]
```

### `models.prophet`

Configures the Meta Prophet time-series forecasting model.

```yaml
models:
  prophet:
    [enabled: <boolean> | default = false]

    # Seasonality mode.
    # Accepted values: additive, multiplicative.
    [seasonality_mode: <string> | default = "additive"]

    # Flexibility of the trend changepoints. Higher values allow more trend changes.
    [changepoint_prior_scale: <float> | default = 0.05]

    # Flexibility of the seasonality components. Higher values allow larger seasonal fluctuations.
    [seasonality_prior_scale: <float> | default = 10.0]

    [yearly_seasonality: <boolean> | default = false]
    [weekly_seasonality: <boolean> | default = true]
    [daily_seasonality: <boolean> | default = true]
```

### `models.pytorch`

Configures the PyTorch LSTM-based model.

```yaml
models:
  pytorch:
    [enabled: <boolean> | default = false]

    # Device used for training.
    # Accepted values: auto, cpu, mps, cuda.
    # auto selects CUDA if available, then MPS, then CPU.
    [device: <string> | default = "auto"]

    # Number of independent training runs whose predictions are averaged.
    # Increase to 3 or more for production-quality ensembles.
    [ensemble_runs: <int> | default = 1]

    # Number of time steps fed into the model per forward pass.
    # 1440 corresponds to one full day of minute-level data.
    [sequence_length: <int> | default = 60]

    # Number of hidden units in each LSTM layer.
    [hidden_size: <int> | default = 64]

    # Number of stacked LSTM layers.
    [num_layers: <int> | default = 2]

    # Dropout probability applied between LSTM layers.
    # Accepted range: 0.0 to 1.0.
    [dropout: <float> | default = 0.2]

    [learning_rate: <float> | default = 0.001]

    # L2 regularization coefficient applied by the optimizer.
    [weight_decay: <float> | default = 0.0]

    # Number of samples per training batch.
    [batch_size: <int> | default = 128]

    [epochs: <int> | default = 20]

    # Number of epochs without validation improvement before stopping training early.
    [early_stopping_patience: <int> | default = 5]

    [random_seed: <int> | default = 42]
```

## `telemetry`

Configures OpenTelemetry export for metrics and traces emitted by the application itself.

```yaml
telemetry:
  # OTLP gRPC endpoint where telemetry data is sent.
  # Env: OTEL_EXPORTER_OTLP_ENDPOINT
  [endpoint: <string> | default = "http://localhost:4317"]

  # Deployment environment label attached to all telemetry (e.g., production, staging).
  # Env: OTEL_ENV
  [env: <string> | default = "development"]

  # Env: OTEL_SERVICE_NAME
  [service_name: <string> | default = "dl-obs"]

  # Env: OTEL_SERVICE_NAMESPACE
  [service_namespace: <string> | default = "dl-obs"]

  # Env: OTEL_SERVICE_VERSION
  [service_version: <string> | default = "0.1.0"]
```

## Related documentation

- [Architecture](./architecture.md) — pipeline architecture and data flow
- [CLI](./cli.md) — Iceberg catalog management CLI
- [Local stack](./local-stack.md) — local Docker Compose stack for development
