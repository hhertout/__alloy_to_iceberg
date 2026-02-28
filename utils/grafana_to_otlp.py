from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, InstrumentationScope, KeyValue
from opentelemetry.proto.metrics.v1.metrics_pb2 import (
    Gauge,
    Metric,
    NumberDataPoint,
    ResourceMetrics,
    ScopeMetrics,
)
from opentelemetry.proto.resource.v1.resource_pb2 import Resource

from src.client.grafana_dto import GrafanaQueryResponse

_MS_TO_NS = 1_000_000


def convert_grafana_resp_to_otlp(
    grafana_response: GrafanaQueryResponse,
    ref_id_to_name: str | None = None,
    resource_attrs: dict[str, str] | None = None,
) -> ExportMetricsServiceRequest:
    """Convert a Grafana query response to an OTLP ExportMetricsServiceRequest.

    Each ref_id in the response becomes one Metric of type Gauge. Multiple frames
    under the same ref_id (one per label combination) are merged into a single Metric,
    with each frame's labels propagated as NumberDataPoint attributes.

    Timestamps are converted from epoch milliseconds (Grafana) to nanoseconds (OTLP).
    Frames with mismatched or missing columns are skipped silently.

    Args:
        grafana_response: Parsed Grafana /api/ds/query response.
        ref_id_to_name: Optional mapping from Grafana ref_id to the metric name
            defined in configs/queries.yaml (the ``id`` field). When a ref_id has
            no entry in the mapping, the ref_id itself is used as the metric name.

    Returns:
        An ExportMetricsServiceRequest ready to be serialised and sent to Kafka.
    """
    metrics: list[Metric] = []

    for ref_id, query_result in grafana_response.results.items():
        metric_name = ref_id_to_name or ref_id
        data_points: list[NumberDataPoint] = []

        for frame in query_result.frames:
            raw = frame.data.values
            if len(raw) != 2:
                continue

            timestamps, values = raw[0], raw[1]
            if not timestamps:
                continue

            # Prometheus labels live in the second schema field (the value column).
            labels: dict[str, str] = {}
            if len(frame.schema.fields) >= 2:
                labels = frame.schema.fields[1].get("labels", {})

            dp_attrs = [
                KeyValue(key=k, value=AnyValue(string_value=str(v))) for k, v in labels.items()
            ]

            for ts, val in zip(timestamps, values, strict=False):
                if ts is None or val is None:
                    continue
                data_points.append(
                    NumberDataPoint(
                        time_unix_nano=int(ts) * _MS_TO_NS,
                        as_double=float(val),
                        attributes=dp_attrs,
                    )
                )

        if not data_points:
            continue

        metrics.append(Metric(name=metric_name, gauge=Gauge(data_points=data_points)))

    resource = Resource(
        attributes=[
            KeyValue(key=k, value=AnyValue(string_value=v))
            for k, v in (resource_attrs or {}).items()
        ]
    )

    return ExportMetricsServiceRequest(
        resource_metrics=[
            ResourceMetrics(
                resource=resource,
                scope_metrics=[
                    ScopeMetrics(
                        scope=InstrumentationScope(name="grafana"),
                        metrics=metrics,
                    )
                ],
            )
        ]
    )
