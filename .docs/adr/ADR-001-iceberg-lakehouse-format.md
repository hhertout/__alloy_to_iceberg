---
title: "ADR-001: Apache Iceberg as lakehouse table format"
status: accepted
date: 2026-03-15
---

# ADR-001: Apache Iceberg as lakehouse table format

## Context

The project ingests observability data (metrics and logs) from Grafana via Kafka and stores it for two purposes:

- **Training reads:** DuckDB scans time-windowed slices to build ML training datasets.
- **Operational queries:** Ad-hoc exploration and debugging of raw ingested data.

The data arrives as small batches (3 MB default) from the integration pipeline and accumulates over months. The schema evolves as new resource attributes or metric dimensions are added.

We need a storage format that supports:

- Schema evolution without rewriting historical data.
- Partition pruning for efficient time-range scans.
- ACID writes from a single-writer pipeline.
- Compatibility with multiple query engines (DuckDB, Spark, Trino).
- Support for multiple catalog backends (Postgres, Polaris, Unity Catalog).

## Alternatives considered

### Raw Parquet files on blob storage

The simplest option. Parquet files are written to a date-based folder structure and read directly.

- **Pros:** No catalog dependency, simple to implement.
- **Cons:** No schema evolution, no ACID guarantees, no partition pruning metadata, readers must list blobs and parse folder names. This was the original approach in the legacy `push_to_blob.py` pipeline.

### Delta Lake

Open-source lakehouse format from Databricks with a JSON-based transaction log.

- **Pros:** Mature Python SDK (`delta-rs`), good Spark integration, ACID writes.
- **Cons:** Weaker support for non-Databricks catalogs. The REST catalog spec is Iceberg-native, and both Polaris and Unity expose Iceberg REST endpoints. Delta's catalog story is more fragmented.

### Apache Hudi

Lakehouse format focused on upserts and change data capture.

- **Pros:** Excellent for CDC workloads with record-level upserts.
- **Cons:** Overkill for append-only time series. Python SDK maturity is behind Iceberg's `pyiceberg`. Catalog support is narrower.

## Decision

Use **Apache Iceberg** as the table format, managed via `pyiceberg`.

## Rationale

- **Schema evolution:** Iceberg supports additive schema changes (new columns, type promotions) via `update_schema()` without rewriting data. The project uses this through versioned migration methods (`__v01`, `__v02`).
- **Multi-catalog support:** `pyiceberg` natively supports Postgres, REST (Polaris, Unity), and Glue catalogs with a uniform API. The project's `CatalogClient` switches backend via configuration.
- **Partition pruning:** Iceberg's metadata tracks partition stats per file, enabling DuckDB to skip irrelevant partitions at scan time when `row_filter` is applied.
- **Compression:** Table properties set `write.parquet.compression-codec: zstd`, achieving ~2.15 bytes/row for metrics data.
- **Ecosystem:** DuckDB reads Iceberg via `pyiceberg`'s `scan().to_duckdb()`. Spark, Trino, and Flink can also read the same tables if needed later.

## Consequences

- The project depends on `pyiceberg` and its transitive dependencies (`pyarrow`, `adlfs` for Azure).
- Small-file compaction is required over time since the pipeline appends small batches. A periodic `rewrite_files()` or external compaction job should be scheduled.
- Snapshot expiry must be configured to prevent metadata growth (`history.expire.max-snapshot-age-ms`).

## Related

- [ADR-005: Partitioning strategy](./ADR-005-partitioning-strategy.md)
- [ADR-006: Storage backend](./ADR-006-storage-backend.md)
