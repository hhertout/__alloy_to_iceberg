from logging import Logger
from typing import Any, ClassVar, Literal

import polars as pl
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from pydantic import BaseModel, Field

from configs.base import IntegrationSettings
from src.processing.oltp_parser import OtlpJsonParser
from utils.telemetry import get_meter

_meter = get_meter("ml_obs.integration_pipeline")

_message_raw_gauge = _meter.create_gauge(
    "ml.integration_pipeline.message_rows",
    description="Number of rows in the incoming message before filtering",
)
_filtered_rows_gauge = _meter.create_gauge(
    "ml.integration_pipeline.filtered_rows",
    description="Number of rows filtered out by the pipeline",
)


class KVPair(BaseModel):
    key: str
    value: str | None = None


class MetricRow(BaseModel):
    timestamp: int
    name: str = Field(serialization_alias="__name__")
    value: float | None
    service_name: str | None
    service_namespace: str | None = None
    k8s_namespace_name: str | None = None
    cluster_name: str | None = None
    host: str | None = None
    env: str | None = None
    resource_attributes: list[KVPair]
    attributes: list[KVPair]


class LogRow(BaseModel):
    timestamp: int
    line: str | None
    service_name: str | None = None
    service_namespace: str | None = None
    k8s_namespace_name: str | None = None
    cluster_name: str | None = None
    host: str | None = None
    env: str | None = None
    resource_attributes: list[KVPair]
    attributes: list[KVPair]


class IntegrationPipelineProcessor:
    """Process incoming OTLP JSON messages into a clean Polars DataFrame ready for batching and writing."""

    def __init__(self, logger: Logger, settings: IntegrationSettings):
        self.log = logger
        self.settings = settings
        self.parser = OtlpJsonParser()

    _SCHEMA: ClassVar[dict[str, Any]] = {
        "timestamp": pl.Datetime("us", "UTC"),
        "__name__": pl.String,
        "value": pl.Float64,
        "service_name": pl.String,
        "service_namespace": pl.String,
        "k8s_namespace_name": pl.String,
        "cluster_name": pl.String,
        "host": pl.String,
        "env": pl.String,
        "resource_attributes": pl.List(pl.Struct({"key": pl.String, "value": pl.String})),
        "attributes": pl.List(pl.Struct({"key": pl.String, "value": pl.String})),
    }

    _LOG_SCHEMA: ClassVar[dict[str, Any]] = {
        "timestamp": pl.Datetime("us", "UTC"),
        "line": pl.String,
        "service_name": pl.String,
        "service_namespace": pl.String,
        "k8s_namespace_name": pl.String,
        "cluster_name": pl.String,
        "host": pl.String,
        "env": pl.String,
        "resource_attributes": pl.List(pl.Struct({"key": pl.String, "value": pl.String})),
        "attributes": pl.List(pl.Struct({"key": pl.String, "value": pl.String})),
    }

    def _any_value(self, v: Any) -> str | int | float | bool | bytes | None:
        """Extract the typed value from an OTLP AnyValue protobuf message."""
        kind = v.WhichOneof("value")
        return getattr(v, kind) if kind else None

    def _flatten_attrs(self, attributes: Any) -> dict[str, str | int | float | bool | bytes | None]:
        """Flatten a protobuf repeated KeyValue field into a plain dict."""
        return {a.key: self._any_value(a.value) for a in attributes}

    def _attrs_to_kv_list(self, attributes: Any) -> list[KVPair]:
        """Convert protobuf repeated KeyValue to a list of KVPair (Iceberg map-compatible)."""
        return [
            KVPair(key=a.key, value=str(v) if (v := self._any_value(a.value)) is not None else None)
            for a in attributes
        ]

    def _datapoint_value(self, dp: Any, metric_type: str) -> float | None:
        """Extract the numeric value from a dataPoint protobuf message."""
        if metric_type in ("gauge", "sum"):
            kind = dp.WhichOneof("value")  # "as_double" | "as_int"
            return float(getattr(dp, kind)) if kind else None
        if metric_type in ("histogram", "summary"):
            return float(dp.sum)
        return None

    def _metrics_to_df(self, msg: ExportMetricsServiceRequest) -> pl.DataFrame:
        """Parse an OTLP JSON payload into a flat Polars DataFrame with a stable Iceberg-compatible schema.
        Output columns
        --------------
        - ``timestamp``           : Datetime[ns, UTC]  — from time_unix_nano, partition key
        - ``__name__``            : String             — metric name, partition key
        - ``value``               : Float64            — numeric value
        - ``service_name``        : String             — promoted from resource.attributes["service.name"]
        - ``resource_attributes`` : Map[String, String] — full resource attributes as a map
        - ``attributes``          : Map[String, String] — full dataPoint attributes as a map
        """
        rows: list[MetricRow] = []

        for rm in msg.resource_metrics:
            resource_raw = self._flatten_attrs(rm.resource.attributes)
            raw_service = resource_raw.get("service.name")
            raw_deployement_env = resource_raw.get("deployment.environment")
            raw_env = resource_raw.get("env")
            raw_service_namespace = resource_raw.get("service.namespace")
            raw_k8s_namespace = resource_raw.get("k8s.namespace.name")
            raw_cluster = resource_raw.get("cluster.name")
            raw_host = resource_raw.get("host")
            raw_host_name = resource_raw.get("host.name")

            service_name: str | None = str(raw_service) if raw_service is not None else None
            service_namespace: str | None = (
                str(raw_service_namespace) if raw_service_namespace is not None else None
            )
            k8s_namespace_name: str | None = (
                str(raw_k8s_namespace) if raw_k8s_namespace is not None else None
            )
            cluster_name: str | None = str(raw_cluster) if raw_cluster is not None else None
            host: str | None = str(raw_host) if raw_host is not None else None
            host_name: str | None = str(raw_host_name) if raw_host_name is not None else None
            env: str | None = str(raw_env) if raw_env is not None else None
            deployment_env: str | None = (
                str(raw_deployement_env) if raw_deployement_env is not None else None
            )

            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    metric_type = metric.WhichOneof("data")
                    if metric_type is None:
                        continue

                    for dp in getattr(metric, metric_type).data_points:
                        rows.append(
                            MetricRow(
                                timestamp=dp.time_unix_nano,
                                name=metric.name,
                                value=self._datapoint_value(dp, metric_type),
                                service_name=service_name,
                                service_namespace=service_namespace,
                                k8s_namespace_name=k8s_namespace_name,
                                cluster_name=cluster_name,
                                host=host_name or host or None,
                                env=env or deployment_env or None,
                                resource_attributes=self._attrs_to_kv_list(rm.resource.attributes),
                                attributes=self._attrs_to_kv_list(dp.attributes),
                            )
                        )

        if not rows:
            return pl.DataFrame(schema=self._SCHEMA)

        df = pl.from_dicts([row.model_dump(by_alias=True) for row in rows], schema=self._SCHEMA)
        df = df.with_columns(
            pl.col("timestamp")
            .cast(pl.Int64)
            .cast(pl.Datetime("ns", "UTC"))
            .cast(pl.Datetime("us", "UTC"))
        )
        return df

    def _kv_match(self, col: str, kv: dict[str, str]) -> pl.Expr:
        """AND of all key=regex_pattern checks inside a list-of-structs column."""
        if not kv:
            return pl.lit(True)
        return pl.all_horizontal(
            *[
                pl.col(col)
                .list.eval(
                    pl.element().struct.field("key").eq(k)
                    & pl.element().struct.field("value").str.contains(v)
                )
                .list.any()
                for k, v in kv.items()
            ]
        )

    def _logs_to_df(self, msg: ExportLogsServiceRequest) -> pl.DataFrame:
        """Parse an OTLP logs payload into a Polars DataFrame matching the Iceberg log schema."""
        rows: list[LogRow] = []

        for rl in msg.resource_logs:
            resource_raw = self._flatten_attrs(rl.resource.attributes)
            service_name = str(v) if (v := resource_raw.get("service.name")) is not None else None
            service_namespace = str(v) if (v := resource_raw.get("service.namespace")) is not None else None
            k8s_namespace_name = str(v) if (v := resource_raw.get("k8s.namespace.name")) is not None else None
            cluster_name = str(v) if (v := resource_raw.get("cluster.name")) is not None else None
            host = str(v) if (v := resource_raw.get("host.name") or resource_raw.get("host")) is not None else None
            env = str(v) if (v := resource_raw.get("env") or resource_raw.get("deployment.environment")) is not None else None

            for sl in rl.scope_logs:
                for lr in sl.log_records:
                    body_kind = lr.body.WhichOneof("value")
                    line = str(getattr(lr.body, body_kind)) if body_kind else None

                    rows.append(
                        LogRow(
                            timestamp=lr.time_unix_nano or lr.observed_time_unix_nano,
                            line=line,
                            service_name=service_name,
                            service_namespace=service_namespace,
                            k8s_namespace_name=k8s_namespace_name,
                            cluster_name=cluster_name,
                            host=host,
                            env=env,
                            resource_attributes=self._attrs_to_kv_list(rl.resource.attributes),
                            attributes=self._attrs_to_kv_list(lr.attributes),
                        )
                    )

        if not rows:
            return pl.DataFrame(schema=self._LOG_SCHEMA)

        df = pl.from_dicts([row.model_dump() for row in rows], schema=self._LOG_SCHEMA)
        df = df.with_columns(
            pl.col("timestamp")
            .cast(pl.Int64)
            .cast(pl.Datetime("ns", "UTC"))
            .cast(pl.Datetime("us", "UTC"))
        )
        return df

    def _filter_metrics(self, df: pl.DataFrame) -> pl.DataFrame:
        _raw_count = len(df)
        includes = self.settings.metrics.include
        if not includes:
            _filtered_rows_gauge.set(0)
            return df

        combined = pl.lit(False)
        for metrics in includes:
            combined = combined | (
                (pl.col("__name__") == metrics.name)
                & self._kv_match("resource_attributes", metrics.resource_attributes)
                & self._kv_match("attributes", metrics.attributes)
            )

        filtered_df = df.filter(combined)
        _filtered_rows_gauge.set(_raw_count - len(filtered_df))

        return filtered_df

    def process_message(self, msg: str | bytes) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Parse an OTLP JSON message and return (metrics_df, logs_df)."""
        self.log.debug("Starting processing message")
        self.log.debug("Parsing OTLP JSON message into metrics and logs")

        metrics_proto, logs_proto = self.parser.parse(msg)

        self.log.debug("Converting parsed metrics to Polars DataFrame")
        metrics_df = self._metrics_to_df(metrics_proto)
        _message_raw_gauge.set(len(metrics_df))

        self.log.debug("Filtering DataFrame based on configuration")
        metrics_df = self._filter_metrics(metrics_df)

        self.log.debug("Converting parsed logs to Polars DataFrame")
        logs_df = self._logs_to_df(logs_proto)

        return metrics_df, logs_df
