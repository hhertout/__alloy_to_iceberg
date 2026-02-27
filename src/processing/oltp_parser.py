from google.protobuf.json_format import Parse
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest


class OtlpJsonParser:
    def parse(
        self, json_str: str | bytes
    ) -> tuple[ExportMetricsServiceRequest, ExportLogsServiceRequest]:
        metrics = Parse(json_str, ExportMetricsServiceRequest(), ignore_unknown_fields=True)
        logs = Parse(json_str, ExportLogsServiceRequest(), ignore_unknown_fields=True)

        return metrics, logs
