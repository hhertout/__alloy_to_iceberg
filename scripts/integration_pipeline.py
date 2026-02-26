from logging import Logger
from typing import Any, ClassVar

import polars as pl
from confluent_kafka import Consumer, KafkaError
from dotenv import load_dotenv
from google.protobuf.json_format import Parse
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from pydantic import BaseModel, Field
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import (
    DoubleType,
    ListType,
    NestedField,
    StringType,
    StructType,
    TimestamptzType,
)

from configs.base import (
    AzureSettings,
    IntegrationSettings,
    load_integration_settings,
    load_storage_settings,
)
from utils import get_logger
from utils.askii_art import print_ascii_art
from utils.telemetry import get_meter, setup_telemetry, shutdown_telemetry

_meter = get_meter("ml_obs.integration_pipeline")

_message_raw_gauge = _meter.create_gauge(
    "ml.integration_pipeline.message_rows",
    description="Number of rows in the incoming message before filtering",
)
_filtered_rows_gauge = _meter.create_gauge(
    "ml.integration_pipeline.filtered_rows",
    description="Number of rows filtered out by the pipeline",
)

METRICS_SCHEMA = Schema(
    NestedField(1, "timestamp", TimestamptzType(), required=False),
    NestedField(2, "__name__", StringType(), required=False),
    NestedField(3, "value", DoubleType(), required=False),
    NestedField(4, "service_name", StringType(), required=False),
    NestedField(
        5,
        "resource_attributes",
        ListType(
            6,
            StructType(
                NestedField(7, "key", StringType(), required=False),
                NestedField(8, "value", StringType(), required=False),
            ),
            element_required=False,
        ),
        required=False,
    ),
    NestedField(
        9,
        "attributes",
        ListType(
            10,
            StructType(
                NestedField(11, "key", StringType(), required=False),
                NestedField(12, "value", StringType(), required=False),
            ),
            element_required=False,
        ),
        required=False,
    ),
)


class KVPair(BaseModel):
    key: str
    value: str | None = None


class MetricRow(BaseModel):
    timestamp: int
    name: str = Field(serialization_alias="__name__")
    value: float | None
    service_name: str | None
    resource_attributes: list[KVPair]
    attributes: list[KVPair]


class OtlpJsonParser:
    def parse(
        self, json_str: str | bytes
    ) -> tuple[ExportMetricsServiceRequest, ExportLogsServiceRequest]:
        metrics = Parse(json_str, ExportMetricsServiceRequest(), ignore_unknown_fields=True)
        logs = Parse(json_str, ExportLogsServiceRequest(), ignore_unknown_fields=True)

        return metrics, logs


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
        - ``resource_attributes`` : List[Struct{key, value}] — full resource attributes as a map
        - ``attributes``          : List[Struct{key, value}] — full dataPoint attributes as a map
        """
        rows: list[MetricRow] = []

        for rm in msg.resource_metrics:
            resource_raw = self._flatten_attrs(rm.resource.attributes)
            raw_service = resource_raw.get("service.name")
            service_name: str | None = str(raw_service) if raw_service is not None else None
            resource_kv = self._attrs_to_kv_list(rm.resource.attributes)

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
                                resource_attributes=resource_kv,
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

    def process_message(self, msg: str | bytes) -> pl.DataFrame:
        self.log.info("Starting processing message")

        self.log.info("Parsing OTLP JSON message into metrics and logs")
        self.log.debug("Parsing message: %s", msg)
        metrics, _ = self.parser.parse(msg)

        self.log.info("Converting parsed metrics to Polars DataFrame")
        df = self._metrics_to_df(metrics)
        _message_raw_gauge.set(len(df))

        self.log.info("Filtering DataFrame based on configuration")
        df = self._filter_metrics(df)
        return df


class Batch:
    """A simple batch accumulator for Polars DataFrames, with a flush method to write out the batch and reset."""

    def __init__(self, settings: IntegrationSettings):
        self.settings = settings
        self.data = pl.DataFrame()
        self.size_bytes: float = 0
        self.size = 0

    def add(self, df: pl.DataFrame) -> None:
        self.data = pl.concat([self.data, df], how="vertical")
        self.size += len(df)
        self.size_bytes += df.estimated_size()

    def flush(self) -> pl.DataFrame:
        data = self.data
        self.data = pl.DataFrame()
        self.size = 0
        self.size_bytes = 0
        return data


class CatalogClient:
    def __init__(self, settings: IntegrationSettings):
        self._settings = settings
        self._backend_settings = load_storage_settings()

        if settings.iceberg.postgres is not None:
            self.kind = "pg"
        elif settings.iceberg.polaris is not None:
            self.kind = "polaris"
        else:
            raise ValueError("Unsupported catalog backend in settings")

        if isinstance(self._backend_settings, AzureSettings):
            self.storage_kind = "azure"
        else:
            self.storage_kind = "s3"

    def load_catalog(self) -> None:
        args: dict[str, str | None] = {}

        if isinstance(self._backend_settings, AzureSettings):
            args = {
                "catalog-name": self._settings.iceberg.catalog_name,
                "warehouse": f"abfs://{self._backend_settings.container_name}@{self._backend_settings.account_name}.dfs.core.windows.net/warehouse",
                "adls.connection-string": self._backend_settings.connection_string,
            }
        else:
            args = {
                "warehouse": f"s3://{self._backend_settings.bucket_name}/warehouse",
                "s3.endpoint": self._backend_settings.endpoint_url,
                "s3.access-key-id": self._backend_settings.aws_access_key_id,
                "s3.secret-access-key": self._backend_settings.aws_secret_access_key,
                "s3.region": self._backend_settings.region_name,
            }

        if self._settings.iceberg.postgres is not None:
            postgres = self._settings.iceberg.postgres
            args["catalog-type"] = "postgres"
            args["uri"] = postgres.connection_string
        elif self._settings.iceberg.polaris is not None:
            polaris = self._settings.iceberg.polaris
            args["catalog-type"] = "rest"
            args["uri"] = polaris.url
            args["credential"] = polaris.token

        self.catalog = load_catalog(self.kind, **args)

    def create_namespace(self) -> None:
        if self._settings.iceberg.namespace is not None:
            try:
                self.catalog.create_namespace(self._settings.iceberg.namespace)
            except Exception as e:
                if "already exists" in str(e):
                    pass
                else:
                    raise e

    def create_tables(self) -> None:
        identifier = f"{self._settings.iceberg.namespace}.otlp_metrics"
        try:
            self.metrics_table = self.catalog.create_table(identifier, schema=METRICS_SCHEMA)
        except Exception as e:
            if "already exists" in str(e):
                self.metrics_table = self.catalog.load_table(identifier)
            else:
                raise e


def main() -> None:
    load_dotenv()
    print_ascii_art()
    log = get_logger("integration_pipeline")
    log.info("Starting integration pipeline...")

    try:
        integration_settings = load_integration_settings()
        consumer = Consumer(
            {
                "bootstrap.servers": integration_settings.kafka.broker,
                "group.id": integration_settings.kafka.group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,  # commit manuel après flush
            }
        )

        c_client = CatalogClient(integration_settings)
        c_client.load_catalog()
        c_client.create_namespace()
        c_client.create_tables()

        consumer.subscribe([integration_settings.kafka.topic])
        log.info(
            "Kafka consumer initialized and subscribed to topic: %s, consumer group: %s",
            integration_settings.kafka.topic,
            integration_settings.kafka.group_id,
        )

        processor = IntegrationPipelineProcessor(log, integration_settings)
        batch = Batch(integration_settings)

        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                pass
            elif (kafka_err := msg.error()) is not None:
                if kafka_err.code() != KafkaError._PARTITION_EOF:  # type: ignore[attr-defined]
                    log.error("Kafka error: %s", kafka_err)
            else:
                value = msg.value()
                if value is None:
                    continue
                response = processor.process_message(value)
                batch.add(response)

                if batch.size >= integration_settings.batch_size:
                    c_client.metrics_table.append(batch.flush().to_arrow())

    except KeyboardInterrupt:
        log.info("Integration pipeline interrupted. Shutting down...")
    except Exception as e:
        log.exception("Unexpected error in integration pipeline: %s", e)
    finally:
        log.info("Integration pipeline finished.")
        if "consumer" in dir():
            consumer.close()
        shutdown_telemetry()


if __name__ == "__main__":
    setup_telemetry()
    main()
