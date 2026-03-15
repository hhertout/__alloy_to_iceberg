---
title: "ADR-004: DuckDB as training query engine"
status: accepted
date: 2026-03-15
---

# ADR-004: DuckDB as training query engine

## Context

The training pipeline (`scripts/train.py`) needs to read time-windowed slices from Iceberg tables and reshape them into feature matrices for ML models (LSTM, XGBoost, Random Forest, Prophet). The query workload is:

- **Time-range scans:** Read the last N days of metric data filtered by timestamp.
- **Aggregation:** Bucket data into 5-minute intervals and compute averages.
- **Pivot:** Transform rows (one per metric × timestamp) into wide-format columns (one column per metric).
- **Single user:** One training job at a time, running on a single machine (laptop or CI runner).

The query engine must integrate with PyIceberg for table scanning and output Polars DataFrames for downstream feature engineering.

## Alternatives considered

### Direct PyIceberg scan to Polars

Use `pyiceberg.scan().to_arrow()` and then convert to Polars for all transformations.

- **Pros:** No additional dependency. Pure Python/Arrow pipeline.
- **Cons:** Complex aggregation, pivoting, and bucketing logic must be written in Polars, which is verbose compared to SQL. No query optimization layer.

### Apache Spark (PySpark)

Distributed query engine with native Iceberg support.

- **Pros:** Battle-tested for large-scale data. Rich SQL support. Handles datasets that don't fit in memory.
- **Cons:** Heavy dependency (JVM, Spark runtime). Overkill for single-node training with datasets that fit in memory (< 1 GB typically). Slow startup time for interactive/CI workloads.

### Trino / Presto

Distributed SQL engine with Iceberg connector.

- **Pros:** Excellent SQL support, can query across catalogs.
- **Cons:** Requires a running Trino cluster. Same operational overhead issue as Spark for single-node workloads.

### Polars SQL

Polars provides a SQL context for DataFrame queries.

- **Pros:** Same dependency as the existing pipeline.
- **Cons:** SQL support is less mature than DuckDB. No native Iceberg integration — still needs PyIceberg scan first.

## Decision

Use **DuckDB** as the training query engine, bridged from PyIceberg via `scan().to_duckdb()`.

## Implementation

The query path in `src/repository/duckdb.py`:

1. PyIceberg scans the Iceberg table with a `row_filter` for time range.
2. `scan().to_duckdb(table_name="metrics_table")` materializes the filtered Arrow batches into a DuckDB in-memory table.
3. A SQL query performs:
   - `time_bucket(INTERVAL '5 minutes', timestamp)` for temporal bucketing.
   - `AVG(value)` grouped by bucket and metric name.
   - `PIVOT` to reshape from long to wide format.
   - `MAP` extraction for resource attributes.
4. The result is fetched as an Arrow table and converted to a Polars DataFrame.

## Rationale

- **Zero infrastructure:** DuckDB runs in-process with no server, no JVM, and no cluster. It starts in milliseconds.
- **SQL expressiveness:** The bucket + aggregate + pivot query is clean and readable in SQL compared to equivalent DataFrame operations.
- **PyIceberg bridge:** The `to_duckdb()` method provides zero-copy Apache Arrow transfer from PyIceberg scans to DuckDB, avoiding serialization overhead.
- **Performance:** DuckDB's vectorized execution engine handles the training dataset sizes (days to weeks of 5-minute metrics) efficiently on a single core.
- **Ecosystem:** DuckDB's SQL dialect supports advanced features (`time_bucket`, `PIVOT`, `MAP`) that map directly to the data reshaping needs.

## Consequences

- DuckDB adds a native dependency (`duckdb` Python package with C++ extension). This is a lightweight dependency (~30 MB) but must be compatible with the target platform.
- The training query in `duckdb.py` uses a hardcoded 7-day window (`WHERE timestamp > now() - INTERVAL '7 days'`). This should become configurable to allow experimentation with different training windows.
- Partition pruning depends on PyIceberg pushing the `row_filter` down to metadata — the current implementation should be verified to ensure Iceberg file-level pruning is active before rows reach DuckDB.
- If datasets grow beyond single-node memory, a migration path to Spark or distributed DuckDB (via MotherDuck or DuckDB extensions) exists without changing the Iceberg storage layer.

## Related

- [ADR-001: Iceberg as lakehouse format](./ADR-001-iceberg-lakehouse-format.md)
- [ADR-005: Partitioning strategy](./ADR-005-partitioning-strategy.md)
