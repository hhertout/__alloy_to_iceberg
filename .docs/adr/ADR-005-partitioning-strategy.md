---
title: "ADR-005: Day-based partitioning strategy"
status: accepted
date: 2026-03-15
---

# ADR-005: Day-based partitioning strategy

## Context

Iceberg tables storing metrics and logs are append-only and grow continuously. The primary query pattern is time-range filtering: the training pipeline reads the last N days, and operational queries typically scope to a specific date range.

Without partitioning, every query scans all data files. With observability data accumulating daily, this becomes increasingly expensive.

The partitioning strategy must balance:

- **Query performance:** Prune as many files as possible for time-range scans.
- **File size:** Partitions shouldn't produce too many small files (< 1 MB) or too few large files (> 1 GB).
- **Write throughput:** Partition assignment during writes shouldn't add significant overhead.
- **Compaction cost:** Fewer partitions per day reduces the compaction surface.

## Alternatives considered

### No partitioning (flat)

All data files in a single partition.

- **Pros:** Simplest. No partition key management.
- **Cons:** No file pruning — every scan reads all files. Query cost grows linearly with total data volume.

### Hour-based partitioning

Partition by `hours(timestamp)` — one partition per hour.

- **Pros:** Finer-grained pruning for sub-day queries.
- **Cons:** With the current ingest rate (~2.15 bytes/row, batch sizes of 3 MB), hourly partitions produce many small files (< 1 MB each). This increases metadata overhead and compaction frequency. The training query reads 7+ days, so hour-level granularity provides minimal benefit over day-level.

### Month-based partitioning

Partition by `months(timestamp)`.

- **Pros:** Fewer partitions, larger files.
- **Cons:** Too coarse for the typical query pattern. A 7-day training window on the boundary of two months reads two entire month-partitions. No pruning benefit for daily operations.

### Composite partitioning (day + service name)

Partition by `days(timestamp)` and `service.name`.

- **Pros:** Enables pruning by both time and service.
- **Cons:** The number of services is potentially unbounded. Each new service creates new partitions across all days, leading to a combinatorial explosion of small files. The training query reads all services, so service-level pruning doesn't help the primary workload.

## Decision

Use **day-based partitioning** with `DayTransform` on the `timestamp` column for both metrics and logs tables.

## Implementation

Partition specs are defined in the schema modules:

- `src/integration/schema/metric.py` — `METRIC_PARTITION_SPEC` with `DayTransform()` on `timestamp` (source_id=1).
- `src/integration/schema/log.py` — `LOG_PARTITION_SPEC` with `DayTransform()` on `timestamp` (source_id=1).

The `TableManager` passes these specs to `catalog.create_table()` at table creation time. Iceberg automatically routes rows to the correct daily partition during writes.

## Rationale

- **Right granularity for the workload:** Training reads 7-day windows. Daily partitions mean 7 files are scanned instead of the entire table. Operational queries by date are also well-served.
- **File sizes:** With 3 MB batches and multiple flushes per day, daily partitions accumulate files in the 10–100 MB range after compaction — well within the optimal Parquet file size.
- **Schema simplicity:** A single partition dimension keeps metadata compact and compaction straightforward. No need to manage cardinality of secondary partition keys.
- **Iceberg hidden partitioning:** The `DayTransform` is an Iceberg transform, not a physical column. Users query with `timestamp > X` and Iceberg prunes automatically — no need to add a `date` column to the schema.

## Consequences

- Queries that don't filter by timestamp (for example, "find all data for service X") scan all partitions. If this becomes a common pattern, a secondary index or alternative table layout may be needed.
- Small-file compaction should be scheduled per partition. Since each day's partition is closed after midnight, compaction can run on the previous day's partition as a batch job.
- If ingest rates increase significantly (for example, 100× current throughput), hour-based partitioning should be reconsidered to keep per-partition file counts manageable.

## Related

- [ADR-001: Iceberg as lakehouse format](./ADR-001-iceberg-lakehouse-format.md)
- [ADR-004: DuckDB query engine](./ADR-004-duckdb-query-engine.md)
