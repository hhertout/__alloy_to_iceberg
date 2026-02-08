"""OpenTelemetry setup for logs and metrics export via OTLP."""

import logging
import os

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

_logger_provider: LoggerProvider | None = None
_meter_provider: MeterProvider | None = None
_default_attributes: dict[str, str] = {}

_DEFAULT_ENDPOINT = "http://localhost:4317"
_DEFAULT_ENV = "development"
_SERVICE_NAME = "dl-obs"
_SERVICE_NAMESPACE = "dl-obs"
_SERVICE_VERSION = "0.1.0"


def setup_telemetry(
    otlp_endpoint: str | None = None,
) -> LoggingHandler:
    """Initialize OpenTelemetry log and metric providers with OTLP export.

    Args:
        service_name: The service name for OTel resource attributes.
        otlp_endpoint: OTLP gRPC endpoint. Falls back to
            ``OTEL_EXPORTER_OTLP_ENDPOINT`` env var, then ``http://localhost:4317``.

    Returns:
        A ``LoggingHandler`` that can be attached to Python's ``logging``.
    """
    global _logger_provider, _meter_provider, _default_attributes

    if otlp_endpoint is None:
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_ENDPOINT)

    env = os.environ.get("OTEL_ENV", _DEFAULT_ENV)
    service_name = os.environ.get("OTEL_SERVICE_NAME", _SERVICE_NAME)
    service_namespace = os.environ.get("OTEL_SERVICE_NAMESPACE", _SERVICE_NAMESPACE)
    service_version = os.environ.get("OTEL_SERVICE_VERSION", _SERVICE_VERSION)
    
    # Silence the OTLP exporter's retry/failure logs when the collector is unreachable.
    logging.getLogger("opentelemetry.exporter.otlp.proto.grpc.exporter").setLevel(
        logging.CRITICAL
    )

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": env,
            "service.namespace": service_namespace,
        }
    )

    _default_attributes = {
        "service.name": service_name,
        "service.version": service_version,
        "service.namespace": service_namespace,
        "environment": env,
    }

    # --- Logs ---
    log_exporter = OTLPLogExporter(endpoint=otlp_endpoint, insecure=True)
    _logger_provider = LoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    # --- Metrics ---
    metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
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
