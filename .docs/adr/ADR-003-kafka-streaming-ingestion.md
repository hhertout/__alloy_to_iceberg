---
title: "ADR-003: Kafka for streaming ingestion"
status: accepted
date: 2026-03-15
---

# ADR-003: Kafka for streaming ingestion

## Context

The metrics producer collects observability data from Grafana on a scheduled basis and must deliver it to the integration pipeline that writes Iceberg tables. The two stages run as separate processes and may operate at different speeds.

Requirements:

- **Decoupling:** The producer shouldn't block waiting for the integration pipeline.
- **Durability:** Messages must survive process restarts. No data loss on pipeline crashes.
- **Ordering:** Per-topic ordering is sufficient (single producer, single consumer group).
- **Throughput:** Moderate — a few thousand messages per minute, each a few hundred KB.

## Alternatives considered

### Direct Iceberg write from the producer

The producer converts Grafana responses and writes directly to Iceberg tables, eliminating the message bus.

- **Pros:** Simpler architecture, one fewer component.
- **Cons:** Tight coupling between collection and storage. No backpressure mechanism. If the producer is faster than disk writes, data is either lost or blocks the collection loop. Schema evolution and table management logic leaks into the producer.

### Redis Streams

Lightweight in-memory streaming with consumer groups.

- **Pros:** Low latency, simple deployment.
- **Cons:** Data resides in memory. Persistence (RDB/AOF) is less battle-tested than Kafka's durability model for production workloads. No native partition-based parallelism.

### RabbitMQ

Mature message broker with flexible routing.

- **Pros:** Good Python support (`pika`), flexible exchange patterns.
- **Cons:** Messages are acknowledged and removed — no replay capability. Not designed for log-structured streaming where consumers may need to re-read history.

## Decision

Use **Apache Kafka** (`confluent-kafka`) as the message bus between the producer and the integration pipeline.

## Configuration

Two Kafka topics are configured:

- `metrics_topic` — OTLP metric messages.
- `logs_topic` — OTLP log messages.

Consumer configuration:

- `enable.auto.commit: false` — manual offset commits after successful Iceberg flush.
- `auto.offset.reset: earliest` — on first join, consume from the beginning.
- Consumer polls in a loop, accumulating messages into a `BatchAccumulator` until the size threshold (`batch_max_size_mb`, default 3 MB) is reached, then flushes to Iceberg and commits offsets.

Producer configuration:

- Messages are serialized as OTLP protobuf bytes (`SerializeToString()`).
- `flush()` is called after each batch of messages to ensure delivery.

## Rationale

- **At-least-once semantics:** Manual offset commits after Iceberg flush ensure that a crash before commit causes re-delivery on restart. Iceberg's snapshot isolation handles duplicate writes gracefully — duplicates create extra rows but don't corrupt state. Deduplication can be added later if needed.
- **Replay capability:** Kafka retains messages for a configurable period (`retention.ms`). If the integration pipeline needs to reprocess data (schema change, bug fix), it can reset offsets and replay.
- **Operational maturity:** Kafka is a proven component for streaming ingestion in production environments. `confluent-kafka` provides a performant C-backed Python client.
- **Decoupling:** The producer and consumer can be scaled, restarted, or upgraded independently.
- **Multi-consumer fan-out:** Kafka topics support multiple independent consumer groups reading the same stream of messages. Today two consumers are plugged into the same data source: the **integration pipeline** (writes to Iceberg for storage and training) and the **prediction pipeline** (runs inference in near real-time). Each consumer group maintains its own offsets and progresses independently. Adding a new consumer (for example, an alerting engine or a data-quality monitor) requires zero changes to the producer — it simply joins the topic with a new `group.id`.
In the future, we could hire more consumers into the data flow without trade-offs and this is particularly valuable for scaling analytics and monitoring capabilities, especially for real-time use cases.

## Consequences

- Kafka is a significant operational dependency — it requires deployment, monitoring, and capacity management (the `docker-compose.yml` includes a Kafka service for local development).
- The at-least-once guarantee means duplicates are possible. If exact-once semantics become necessary, transactional producers or deduplication at the Iceberg layer must be implemented.
- Multiple consumer groups already read from the same topics (integration pipeline and prediction). Each group manages its own offset progression, which means a slow or crashed consumer doesn't block others. This fan-out pattern is a key advantage over point-to-point alternatives like RabbitMQ.
- Within a given consumer group, a single instance is used today. If throughput increases, the topic can be partitioned and multiple instances added to the same group for parallel processing.
- Topic retention and cleanup policies should be configured to match the re-processing window (for example, 7 days).

## Related

- [ADR-002: OTLP canonical format](./ADR-002-otlp-canonical-format.md)
- [ADR-001: Iceberg as lakehouse format](./ADR-001-iceberg-lakehouse-format.md)
