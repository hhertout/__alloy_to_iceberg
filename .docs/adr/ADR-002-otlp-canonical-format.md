---
title: "ADR-002: OTLP as canonical ingestion format"
status: accepted
date: 2026-03-15
---

# ADR-002: OTLP as canonical ingestion format

## Context

The project collects observability data (metrics and logs) from one or more Grafana instances via the Grafana HTTP API. Grafana returns data in its own frame-based JSON format, which varies by datasource (Prometheus, Loki, Tempo).

The data must then be:

1. Published to Kafka for asynchronous ingestion.
2. Deserialized in the integration pipeline into flat Polars DataFrames.
3. Written to Iceberg tables.

We need to choose a canonical wire format for the Kafka messages that bridges the gap between Grafana's query response format and the flat tabular schema needed for Iceberg.

## Alternatives considered

### Keep Grafana frame JSON as-is

Pass Grafana's response directly into Kafka without transformation.

- **Pros:** Zero conversion cost at the producer. No transformation code.
- **Cons:** Grafana's frame format is datasource-specific (Prometheus frames differ from Loki frames). Every downstream consumer must understand multiple frame shapes. Tightly couples the pipeline to Grafana's internal API.

### Custom JSON schema

Define a project-specific JSON schema for metrics and logs.

- **Pros:** Full control over shape and fields.
- **Cons:** No ecosystem support. Requires custom serializers and deserializers. No interoperability with other observability tools.

### OpenTelemetry Protocol (OTLP) Protobuf

Convert Grafana responses to `ExportMetricsServiceRequest` / `ExportLogsServiceRequest` protobuf messages at the producer stage.

- **Pros:** Industry standard, strong ecosystem support, well-defined protobuf schema, self-describing resource attributes, compact binary serialization.
- **Cons:** Conversion step required at the producer. Protobuf dependency.

## Decision

Use **OTLP Protobuf** (`opentelemetry-proto`) as the canonical wire format for all Kafka messages.

Grafana responses are converted to OTLP at the producer stage via `utils/grafana_to_otlp.py`, which maps:

- Grafana metric frames → `NumberDataPoint` with attributes.
- Grafana labels → OTLP `KeyValue` resource/datapoint attributes.
- Timestamps → OTLP `time_unix_nano` (milliseconds to nanoseconds).
- `service.name` → OTLP resource attribute (promoted from labels).

## Rationale

- **Vendor independence:** OTLP is maintained by the OpenTelemetry project and isn't tied to any specific vendor. If the data source changes from Grafana to an OTel Collector, native OTLP flows directly into Kafka without conversion.
- **Schema clarity:** The protobuf schema (`ExportMetricsServiceRequest`) is strongly typed and versioned by the OpenTelemetry project. This eliminates ambiguity about field types and semantics.
- **Compact serialization:** Protobuf serialization is more compact and faster to parse than JSON, which reduces Kafka message sizes and deserialization cost in the integration pipeline.
- **Downstream reuse:** The OTLP messages can be forwarded to any OTLP-compatible backend (Grafana Tempo, Jaeger, etc.) if needed in the future, without additional transformation.

## Consequences

- The producer pipeline (`metrics_producer.py`) must convert every Grafana response to OTLP before publishing. This adds CPU cost proportional to the number of data points.
- The integration pipeline's `processor.py` must parse OTLP protobuf and flatten resource/datapoint attributes into a tabular schema. This "impedance mismatch" between hierarchical OTLP and flat Iceberg rows requires careful mapping.
- The project depends on `opentelemetry-proto` and `protobuf` packages. Protobuf version compatibility must be managed.
- Logs support follows the same pattern (`ExportLogsServiceRequest`), keeping the two signal types consistent.

## Related

- [ADR-003: Kafka streaming ingestion](./ADR-003-kafka-streaming-ingestion.md)
