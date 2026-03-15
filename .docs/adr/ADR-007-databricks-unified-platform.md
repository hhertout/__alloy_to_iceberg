---
title: "ADR-007: Databricks as unified compute and catalog platform"
status: proposed
date: 2026-03-15
---

# ADR-007: Databricks as unified compute and catalog platform

## Context

The current architecture is composed of several independent components:

- **Apache Kafka** for streaming ingestion.
- **PyIceberg + Postgres/Polaris** for catalog and table management.
- **DuckDB** for training data queries.
- **Custom Python scripts** (`scripts/train.py`) for model training.
- **Azure Blob Storage / S3** for data persistence.
- **Local or CI machines** (potentially GPU-equipped) for model training.

Each component is configured, deployed, and maintained separately. As the project grows — more metrics, more models, more consumers — the operational burden increases. Training GPU-intensive deep learning models (PyTorch LSTM) on a dedicated machine requires provisioning, managing CUDA drivers, OS updates, and scheduling.

Databricks provides a unified platform that natively covers the full data and ML lifecycle: ingestion, storage, processing, visualization, and model training — including on-demand GPU clusters. The project already uses Unity Catalog as an Iceberg catalog backend (`catalog.type: unity`), which means the storage layer is already partially Databricks-compatible.

## What Databricks brings to this project

### Unity Catalog as Iceberg catalog

The project supports Unity Catalog as a catalog backend today (`catalog_client.py`, `catalog.type: unity`). Databricks Unity Catalog implements the Iceberg REST catalog spec, which means the existing `pyiceberg` write path is already compatible. Running on Databricks makes Unity Catalog the native catalog — no external Postgres catalog service to maintain.

### Spark for large-scale data processing

DuckDB is well-suited for single-node, in-memory workloads. As data volume grows, the current DuckDB query in `duckdb.py` (7-day scan, pivot, aggregation) may exceed available memory on the training machine.

Databricks runs Apache Spark natively with Unity Catalog integration. The same Iceberg tables can be queried with:

```python
df = spark.read.table("dl_obs.metrics")
```

Spark's distributed execution scales horizontally — adding worker nodes handles data growth without code changes. Spark Structured Streaming can also replace the Kafka consumer → Iceberg write path, providing exactly-once semantics.

### On-demand GPU clusters for model training

Training the PyTorch LSTM model currently requires a GPU-capable machine. On Databricks, GPU clusters are provisioned on demand:

- Single-node GPU clusters (for example, `g4dn.xlarge`, `Standard_NC6s_v3`) are available per-job.
- The cluster starts before the training job and terminates after, so GPU costs are incurred only during training — no idle GPU machine.
- Databricks supports `%pip install` for dependencies and pre-built ML runtime images with PyTorch, CUDA, and cuDNN pre-configured.

This removes the need to maintain a dedicated GPU machine for model generation.

### MLflow for experiment tracking and model registry

Databricks includes a managed MLflow instance. The project already uses multiple model types (PyTorch, XGBoost, Random Forest, Prophet). MLflow would provide:

- Experiment tracking: metrics, hyperparameters, and artifacts per run.
- Model registry: versioned model artifacts with staging/production lifecycle.
- Serving: deploy trained models as REST endpoints for the prediction pipeline.

### Databricks Workflows for pipeline orchestration

The current pipelines are invoked as standalone scripts (`scripts/train.py`, `scripts/integration_pipeline.py`). Databricks Workflows provides:

- DAG-based job scheduling with retry logic and alerting.
- Dependencies between tasks (for example, "run feature engineering, then train, then register model").
- Git-backed job definitions (notebooks or Python scripts from a repository).

### Visualization and data exploration

Databricks SQL provides:

- Dashboards directly on top of Unity Catalog tables.
- SQL queries on metrics and logs without exporting data.
- Alert rules on query results (for example, anomaly counts per service).

This replaces ad-hoc DuckDB queries and Python notebooks for data exploration.

## Decision

The decision is currently **proposed**. Adopting Databricks is an architectural evolution, not an immediate migration. The recommended path is:

1. **Short term:** Continue using the current architecture. The Unity Catalog integration already provides Databricks readiness.
2. **Medium term:** Migrate model training to Databricks on-demand GPU clusters. This eliminates GPU infrastructure management with minimal code changes (PyTorch scripts run unchanged on Databricks Runtime with ML).
3. **Long term:** Evaluate migrating the Kafka consumer (integration pipeline) to Spark Structured Streaming on Databricks for exactly-once semantics and horizontal scalability.

## Rationale

- **Catalog compatibility is already there:** Since the project supports `catalog.type: unity`, the Iceberg tables are already readable from Databricks without any schema migration.
- **Eliminates GPU host management:** On-demand GPU clusters are the highest-value quick win. Training jobs are infrequent and short — paying per-cluster-hour is more cost-effective than a persistent GPU machine.
- **Unified governance:** Unity Catalog provides column-level security, data lineage, and audit logging across all tables — features that would require significant effort to implement independently.
- **Reduces operational surface:** Merging catalog, query engine, training, orchestration, and visualization into one platform reduces the number of independent components to operate.

## Consequences

- **Cost:** Databricks pricing (DBU) can be significant. GPU cluster costs must be weighed against the cost of a dedicated GPU machine. For low-frequency training jobs, on-demand is typically cheaper.
- **Vendor dependency:** Adopting Databricks Workflows and MLflow creates a dependency on the Databricks platform. The Iceberg storage layer and Unity Catalog remain open standards, so the data itself is portable.
- **Migration effort:** Migrating the integration pipeline from `confluent-kafka` + `pyiceberg` to Spark Structured Streaming is non-trivial. It should be treated as a separate decision when throughput justifies it.
- **Local development:** Databricks clusters aren't available locally. The current local stack (Kafka, MinIO, Polaris via `docker-compose.yml`) remains necessary for unit and integration testing without cloud costs.

## Related

- [ADR-001: Iceberg as lakehouse format](./ADR-001-iceberg-lakehouse-format.md)
- [ADR-004: DuckDB query engine](./ADR-004-duckdb-query-engine.md)
- [ADR-006: Storage backend](./ADR-006-storage-backend.md)
