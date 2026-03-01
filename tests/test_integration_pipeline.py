import logging

import polars as pl
import pytest

from configs.base import (
    IcebergSettings,
    IntegrationSettings,
    KafkaSettings,
    MetricFilterSettings,
    MetricsSettings,
)
from scripts.integration_pipeline import IntegrationPipelineProcessor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KAFKA = KafkaSettings(broker="localhost:19092", topic="test", group_id="test-group")
_ICEBERG = IcebergSettings(catalog_name="cat", database_name="db", table_name="tbl")


def _make_settings(includes: list[MetricFilterSettings]) -> IntegrationSettings:
    return IntegrationSettings(
        kafka=_KAFKA,
        iceberg=_ICEBERG,
        metrics=MetricsSettings(include=includes),
    )


def _make_processor(includes: list[MetricFilterSettings]) -> IntegrationPipelineProcessor:
    import logging

    return IntegrationPipelineProcessor(logging.getLogger("test"), _make_settings(includes))


def _make_df(rows: list[dict]) -> pl.DataFrame:
    """Build a minimal DataFrame matching the processor schema."""
    schema = {
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
    return pl.from_dicts(rows, schema=schema)


def _row(
    name: str,
    resource_attrs: dict[str, str] | None = None,
    attrs: dict[str, str] | None = None,
) -> dict:
    ra = resource_attrs or {}
    a = attrs or {}
    return {
        "timestamp": 0,
        "__name__": name,
        "value": 1.0,
        "service_name": ra.get("service.name"),
        "service_namespace": ra.get("service.namespace"),
        "k8s_namespace_name": ra.get("k8s.namespace.name"),
        "cluster_name": ra.get("cluster.name"),
        "host": ra.get("host"),
        "env": ra.get("env"),
        "resource_attributes": [{"key": k, "value": v} for k, v in ra.items()],
        "attributes": [{"key": k, "value": v} for k, v in a.items()],
    }


# ---------------------------------------------------------------------------
# _kv_match
# ---------------------------------------------------------------------------


class TestKvMatch:
    def _eval(self, col: str, kv: dict[str, str], rows: list[dict]) -> list[bool]:
        """Return which rows match the kv filter (using filter context, as in production)."""
        proc = _make_processor([])
        df = _make_df(rows).with_row_index("_i")
        kept = set(df.filter(proc._kv_match(col, kv))["_i"].to_list())
        return [i in kept for i in range(len(rows))]

    def test_empty_kv_always_true(self) -> None:
        rows = [_row("m1"), _row("m2")]
        result = self._eval("attributes", {}, rows)
        assert result == [True, True]

    def test_exact_match_in_attributes(self) -> None:
        rows = [
            _row("m1", attrs={"env": "prod"}),
            _row("m2", attrs={"env": "dev"}),
        ]
        result = self._eval("attributes", {"env": "prod"}, rows)
        assert result == [True, False]

    def test_regex_match_in_attributes(self) -> None:
        rows = [
            _row("m1", attrs={"request": "produce"}),
            _row("m2", attrs={"request": "fetch"}),
            _row("m3", attrs={"request": "produce_v2"}),
        ]
        result = self._eval("attributes", {"request": "produce"}, rows)
        # "produce" matches "produce" and "produce_v2" (str.contains = regex search)
        assert result == [True, False, True]

    def test_regex_alternation(self) -> None:
        rows = [
            _row("m1", attrs={"request": "produce"}),
            _row("m2", attrs={"request": "fetch"}),
            _row("m3", attrs={"request": "delete"}),
        ]
        result = self._eval("attributes", {"request": "produce|fetch"}, rows)
        assert result == [True, True, False]

    def test_multiple_kv_all_must_match(self) -> None:
        rows = [
            _row("m1", attrs={"env": "prod", "region": "eu-west"}),
            _row("m2", attrs={"env": "prod", "region": "us-east"}),
            _row("m3", attrs={"env": "dev", "region": "eu-west"}),
        ]
        result = self._eval("attributes", {"env": "prod", "region": "eu"}, rows)
        assert result == [True, False, False]

    def test_key_absent_does_not_match(self) -> None:
        rows = [
            _row("m1", attrs={"other_key": "prod"}),
        ]
        result = self._eval("attributes", {"env": "prod"}, rows)
        assert result == [False]

    def test_resource_attributes_column(self) -> None:
        rows = [
            _row("m1", resource_attrs={"service.name": "redpanda"}),
            _row("m2", resource_attrs={"service.name": "kafka"}),
        ]
        result = self._eval("resource_attributes", {"service.name": "redpanda"}, rows)
        assert result == [True, False]

    def test_empty_attributes_list_does_not_match(self) -> None:
        rows = [_row("m1")]  # no attributes at all
        result = self._eval("attributes", {"env": "prod"}, rows)
        assert result == [False]


# ---------------------------------------------------------------------------
# _filter_metrics
# ---------------------------------------------------------------------------


class TestFilterMetrics:
    def _filter(self, includes: list[MetricFilterSettings], rows: list[dict]) -> pl.DataFrame:
        proc = _make_processor(includes)
        return proc._filter_metrics(_make_df(rows))

    def test_no_includes_returns_all_rows(self) -> None:
        rows = [_row("m1"), _row("m2")]
        result = self._filter([], rows)
        assert len(result) == 2

    def test_filter_by_name_only(self) -> None:
        rows = [_row("cpu_usage"), _row("mem_usage"), _row("cpu_usage")]
        result = self._filter([MetricFilterSettings(name="cpu_usage")], rows)
        assert len(result) == 2
        assert result["__name__"].to_list() == ["cpu_usage", "cpu_usage"]

    def test_filter_by_name_and_resource_attribute(self) -> None:
        rows = [
            _row("http_requests", resource_attrs={"service.name": "api"}),
            _row("http_requests", resource_attrs={"service.name": "worker"}),
            _row("other_metric", resource_attrs={"service.name": "api"}),
        ]
        includes = [
            MetricFilterSettings(name="http_requests", resource_attributes={"service.name": "api"})
        ]
        result = self._filter(includes, rows)
        assert len(result) == 1
        assert result["service_name"][0] == "api"

    def test_filter_by_name_and_attribute(self) -> None:
        rows = [
            _row("latency", attrs={"method": "GET"}),
            _row("latency", attrs={"method": "POST"}),
        ]
        includes = [MetricFilterSettings(name="latency", attributes={"method": "GET"})]
        result = self._filter(includes, rows)
        assert len(result) == 1

    def test_multiple_includes_are_or(self) -> None:
        rows = [
            _row("metric_a"),
            _row("metric_b"),
            _row("metric_c"),
        ]
        includes = [
            MetricFilterSettings(name="metric_a"),
            MetricFilterSettings(name="metric_b"),
        ]
        result = self._filter(includes, rows)
        assert sorted(result["__name__"].to_list()) == ["metric_a", "metric_b"]

    def test_no_match_returns_empty_df(self) -> None:
        rows = [_row("cpu"), _row("mem")]
        result = self._filter([MetricFilterSettings(name="disk")], rows)
        assert len(result) == 0
        assert result.schema == _make_df([]).schema

    def test_regex_on_metric_name_not_supported_exact_match(self) -> None:
        """Metric name uses == (exact), not regex — 'cpu.*' should not match 'cpu_usage'."""
        rows = [_row("cpu_usage")]
        result = self._filter([MetricFilterSettings(name="cpu.*")], rows)
        assert len(result) == 0

    def test_combined_resource_and_datapoint_attributes(self) -> None:
        rows = [
            _row(
                "rpc_latency",
                resource_attrs={"service.name": "redpanda"},
                attrs={"method": "produce"},
            ),
            _row(
                "rpc_latency",
                resource_attrs={"service.name": "redpanda"},
                attrs={"method": "fetch"},
            ),
            _row(
                "rpc_latency", resource_attrs={"service.name": "kafka"}, attrs={"method": "produce"}
            ),
        ]
        includes = [
            MetricFilterSettings(
                name="rpc_latency",
                resource_attributes={"service.name": "redpanda"},
                attributes={"method": "produce"},
            )
        ]
        result = self._filter(includes, rows)
        assert len(result) == 1

    def test_empty_dataframe_returns_empty(self) -> None:
        result = self._filter(
            [MetricFilterSettings(name="cpu")],
            [],
        )
        assert len(result) == 0


# ---------------------------------------------------------------------------
# process_message — integration tests against the real fixture
# ---------------------------------------------------------------------------

FIXTURE_PATH = "tests/fixtures/messages.json"


@pytest.fixture(scope="module")
def fixture_bytes() -> bytes:
    with open(FIXTURE_PATH, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def no_filter_processor() -> IntegrationPipelineProcessor:
    settings = IntegrationSettings(
        kafka=KafkaSettings(broker="localhost:19092", topic="test", group_id="g"),
        iceberg=IcebergSettings(catalog_name="c", database_name="d", table_name="t"),
        metrics=MetricsSettings(include=[]),
    )
    return IntegrationPipelineProcessor(logging.getLogger("test"), settings)


class TestProcessMessage:
    def test_schema_matches_expected(self, no_filter_processor, fixture_bytes) -> None:
        df = no_filter_processor.process_message(fixture_bytes)
        assert df.schema == {
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

    def test_total_datapoints(self, no_filter_processor, fixture_bytes) -> None:
        df = no_filter_processor.process_message(fixture_bytes)
        assert len(df) == 898

    def test_unique_metric_count(self, no_filter_processor, fixture_bytes) -> None:
        df = no_filter_processor.process_message(fixture_bytes)
        assert df["__name__"].n_unique() == 98

    def test_all_rows_have_service_name_redpanda(self, no_filter_processor, fixture_bytes) -> None:
        df = no_filter_processor.process_message(fixture_bytes)
        assert df["service_name"].unique().to_list() == ["redpanda"]

    def test_timestamps_are_utc_datetime(self, no_filter_processor, fixture_bytes) -> None:
        df = no_filter_processor.process_message(fixture_bytes)
        assert df["timestamp"].dtype == pl.Datetime("us", "UTC")
        assert df["timestamp"].null_count() == 0

    def test_known_metric_row_count_and_value(self, no_filter_processor, fixture_bytes) -> None:
        """redpanda_kafka_records_fetched_total has 5 dataPoints, one with value 1674."""
        df = no_filter_processor.process_message(fixture_bytes)
        m = df.filter(pl.col("__name__") == "redpanda_kafka_records_fetched_total")
        assert len(m) == 5
        assert 1674.0 in m["value"].to_list()

    def test_resource_attributes_populated(self, no_filter_processor, fixture_bytes) -> None:
        df = no_filter_processor.process_message(fixture_bytes)
        # Every row must have at least service.name in resource_attributes
        has_service_name = df.select(
            pl.col("resource_attributes")
            .list.eval(pl.element().struct.field("key").eq("service.name"))
            .list.any()
            .alias("ok")
        )["ok"]
        assert has_service_name.all()

    def test_no_filter_returns_all_metrics(self, no_filter_processor, fixture_bytes) -> None:
        df = no_filter_processor.process_message(fixture_bytes)
        assert len(df) == 898

    def test_filter_by_metric_name(self, fixture_bytes) -> None:
        settings = IntegrationSettings(
            kafka=KafkaSettings(broker="localhost:19092", topic="test", group_id="g"),
            iceberg=IcebergSettings(catalog_name="c", database_name="d", table_name="t"),
            metrics=MetricsSettings(
                include=[MetricFilterSettings(name="redpanda_kafka_records_fetched_total")]
            ),
        )
        proc = IntegrationPipelineProcessor(logging.getLogger("test"), settings)
        df = proc.process_message(fixture_bytes)
        assert len(df) == 5
        assert df["__name__"].unique().to_list() == ["redpanda_kafka_records_fetched_total"]

    def test_filter_by_metric_name_and_dp_attribute(self, fixture_bytes) -> None:
        """Keep only fetched records for the 'kafka' namespace (value=1674)."""
        settings = IntegrationSettings(
            kafka=KafkaSettings(broker="localhost:19092", topic="test", group_id="g"),
            iceberg=IcebergSettings(catalog_name="c", database_name="d", table_name="t"),
            metrics=MetricsSettings(
                include=[
                    MetricFilterSettings(
                        name="redpanda_kafka_records_fetched_total",
                        attributes={"redpanda_namespace": "kafka$"},
                    )
                ]
            ),
        )
        proc = IntegrationPipelineProcessor(logging.getLogger("test"), settings)
        df = proc.process_message(fixture_bytes)
        # "kafka$" matches "kafka" but not "kafka_internal"
        assert len(df) == 3
        assert 1674.0 in df["value"].to_list()

    def test_filter_by_resource_attribute(self, fixture_bytes) -> None:
        settings = IntegrationSettings(
            kafka=KafkaSettings(broker="localhost:19092", topic="test", group_id="g"),
            iceberg=IcebergSettings(catalog_name="c", database_name="d", table_name="t"),
            metrics=MetricsSettings(
                include=[
                    MetricFilterSettings(
                        name="redpanda_kafka_records_fetched_total",
                        resource_attributes={"service.name": "redpanda"},
                    )
                ]
            ),
        )
        proc = IntegrationPipelineProcessor(logging.getLogger("test"), settings)
        df = proc.process_message(fixture_bytes)
        assert len(df) == 5

    def test_filter_unknown_metric_returns_empty(self, fixture_bytes) -> None:
        settings = IntegrationSettings(
            kafka=KafkaSettings(broker="localhost:19092", topic="test", group_id="g"),
            iceberg=IcebergSettings(catalog_name="c", database_name="d", table_name="t"),
            metrics=MetricsSettings(include=[MetricFilterSettings(name="does_not_exist")]),
        )
        proc = IntegrationPipelineProcessor(logging.getLogger("test"), settings)
        df = proc.process_message(fixture_bytes)
        assert len(df) == 0
