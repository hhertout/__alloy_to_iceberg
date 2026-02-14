"""OpenTelemetry setup for logs and metrics export via OTLP."""

import logging

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from configs.base import load_telemetry_settings

_logger_provider: LoggerProvider | None = None
_meter_provider: MeterProvider | None = None
_default_attributes: dict[str, str] = {}


def setup_telemetry(
    otlp_endpoint: str | None = None,
) -> LoggingHandler:
    """Initialize OpenTelemetry log and metric providers with OTLP export.

    Args:
        otlp_endpoint: OTLP gRPC endpoint. Falls back to
            ``OTEL_EXPORTER_OTLP_ENDPOINT`` env var, then ``http://localhost:4317``.

    Returns:
        A ``LoggingHandler`` that can be attached to Python's ``logging``.
    """
    global _logger_provider, _meter_provider, _default_attributes

    settings = load_telemetry_settings(otlp_endpoint=otlp_endpoint)

    # Silence the OTLP exporter's retry/failure logs when the collector is unreachable.
    logging.getLogger("opentelemetry.exporter.otlp.proto.grpc.exporter").setLevel(logging.CRITICAL)

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.env,
        }
    )

    _default_attributes = {
        "service.name": settings.service_name,
        "service.version": settings.service_version,
        "service.namespace": settings.service_namespace,
        "environment": settings.env,
    }

    # --- Logs ---
    log_exporter = OTLPLogExporter(endpoint=settings.otlp_endpoint, insecure=True)
    _logger_provider = LoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    # --- Metrics ---
    metric_exporter = OTLPMetricExporter(endpoint=settings.otlp_endpoint, insecure=True)
    metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=15000)
    _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(_meter_provider)

    handler = LoggingHandler(level=logging.NOTSET, logger_provider=_logger_provider)
    return handler


def get_meter(name: str) -> metrics.Meter:
    """Return a ``Meter`` from the global ``MeterProvider``.

    Args:
        name: Meter name (typically the module or component name).

    Returns:
        An OpenTelemetry ``Meter`` instance.
    """
    return metrics.get_meter(name)


def get_default_attributes() -> dict[str, str]:
    """Return default metric attributes (``service.name``, ``deployment.environment``).

    These can be spread into individual metric recordings, e.g.::

        counter.add(1, attributes={**get_default_attributes(), "extra": "value"})
    """
    return dict(_default_attributes)


def shutdown_telemetry() -> None:
    """Flush pending data and shut down OTel providers."""
    global _logger_provider, _meter_provider

    if _logger_provider is not None:
        _logger_provider.shutdown()
        _logger_provider = None

    if _meter_provider is not None:
        _meter_provider.shutdown()
        _meter_provider = None
