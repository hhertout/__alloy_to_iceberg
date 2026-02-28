import pytest
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest

from src.client.grafana_dto import GrafanaQueryResponse
from utils.grafana_to_otlp import convert_grafana_resp_to_otlp

_MS_TO_NS = 1_000_000

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def single_metric_response() -> GrafanaQueryResponse:
    """One ref_id ("A") with two data points."""
    return GrafanaQueryResponse.from_dict(
        {
            "results": {
                "A": {
                    "frames": [
                        {
                            "schema": {"name": "test", "fields": []},
                            "data": {"values": [[1700000000000, 1700000060000], [42.0, 43.0]]},
                        }
                    ]
                }
            }
        }
    )


@pytest.fixture
def multi_metric_response() -> GrafanaQueryResponse:
    """Two ref_ids ("cpu", "mem") each with one data point."""
    return GrafanaQueryResponse.from_dict(
        {
            "results": {
                "cpu": {
                    "frames": [
                        {
                            "schema": {"name": "cpu", "fields": []},
                            "data": {"values": [[1700000000000], [80.0]]},
                        }
                    ]
                },
                "mem": {
                    "frames": [
                        {
                            "schema": {"name": "mem", "fields": []},
                            "data": {"values": [[1700000000000], [55.5]]},
                        }
                    ]
                },
            }
        }
    )


@pytest.fixture
def empty_response() -> GrafanaQueryResponse:
    """Response with no results."""
    return GrafanaQueryResponse.from_dict({"results": {}})


@pytest.fixture
def empty_frame_response() -> GrafanaQueryResponse:
    """Response where the frame contains no data points."""
    return GrafanaQueryResponse.from_dict(
        {
            "results": {
                "A": {
                    "frames": [
                        {"schema": {"name": "test", "fields": []}, "data": {"values": [[], []]}}
                    ]
                }
            }
        }
    )


@pytest.fixture
def invalid_frame_response() -> GrafanaQueryResponse:
    """Response where the frame has only one column (invalid — not 2)."""
    return GrafanaQueryResponse.from_dict(
        {
            "results": {
                "A": {
                    "frames": [
                        {
                            "schema": {"name": "test", "fields": []},
                            "data": {"values": [[1700000000000]]},
                        }
                    ]
                }
            }
        }
    )


@pytest.fixture
def labeled_metric_response() -> GrafanaQueryResponse:
    """One ref_id ('A') with two frames, each carrying different Prometheus labels."""
    return GrafanaQueryResponse.from_dict(
        {
            "results": {
                "A": {
                    "frames": [
                        {
                            "schema": {
                                "name": "test",
                                "fields": [
                                    {"name": "Time", "type": "time"},
                                    {
                                        "name": "Value",
                                        "type": "number",
                                        "labels": {"job": "api", "env": "prod"},
                                    },
                                ],
                            },
                            "data": {"values": [[1700000000000], [42.0]]},
                        },
                        {
                            "schema": {
                                "name": "test",
                                "fields": [
                                    {"name": "Time", "type": "time"},
                                    {
                                        "name": "Value",
                                        "type": "number",
                                        "labels": {"job": "worker", "env": "prod"},
                                    },
                                ],
                            },
                            "data": {"values": [[1700000000000], [55.0]]},
                        },
                    ]
                }
            }
        }
    )


# ── Return type ───────────────────────────────────────────────────────────────


class TestReturnType:
    def test_returns_export_metrics_service_request(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        assert isinstance(result, ExportMetricsServiceRequest)


# ── ResourceMetrics structure ─────────────────────────────────────────────────


class TestResourceMetrics:
    def test_contains_one_resource_metrics(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        assert len(result.resource_metrics) == 1

    def test_resource_has_service_name_attribute(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(
            single_metric_response, resource_attrs={"service.name": "grafana"}
        )
        attrs = {
            kv.key: kv.value.string_value for kv in result.resource_metrics[0].resource.attributes
        }
        assert attrs["service.name"] == "grafana"

    def test_no_resource_attrs_produces_empty_resource(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        assert len(result.resource_metrics[0].resource.attributes) == 0

    def test_scope_name_is_grafana(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        scope = result.resource_metrics[0].scope_metrics[0].scope
        assert scope.name == "grafana"


# ── Metrics mapping ───────────────────────────────────────────────────────────


class TestMetricsMapping:
    def test_single_ref_id_produces_one_metric(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        metrics = result.resource_metrics[0].scope_metrics[0].metrics
        assert len(metrics) == 1

    def test_metric_name_matches_ref_id(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        assert result.resource_metrics[0].scope_metrics[0].metrics[0].name == "A"

    def test_multiple_ref_ids_produce_multiple_metrics(
        self, multi_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(multi_metric_response)
        metrics = result.resource_metrics[0].scope_metrics[0].metrics
        names = {m.name for m in metrics}
        assert names == {"cpu", "mem"}

    def test_metric_type_is_gauge(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        metric = result.resource_metrics[0].scope_metrics[0].metrics[0]
        # HasField checks which oneof is set on the Metric message
        assert metric.HasField("gauge")


# ── Data points ───────────────────────────────────────────────────────────────


class TestDataPoints:
    def test_data_point_count_matches_input(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        points = result.resource_metrics[0].scope_metrics[0].metrics[0].gauge.data_points
        assert len(points) == 2

    def test_timestamps_converted_from_ms_to_ns(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        points = result.resource_metrics[0].scope_metrics[0].metrics[0].gauge.data_points
        assert points[0].time_unix_nano == 1700000000000 * _MS_TO_NS
        assert points[1].time_unix_nano == 1700000060000 * _MS_TO_NS

    def test_values_set_correctly(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        points = result.resource_metrics[0].scope_metrics[0].metrics[0].gauge.data_points
        assert points[0].as_double == 42.0
        assert points[1].as_double == 43.0


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_response_returns_empty_metrics(
        self, empty_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(empty_response)
        metrics = result.resource_metrics[0].scope_metrics[0].metrics
        assert len(metrics) == 0

    def test_empty_frame_is_skipped(self, empty_frame_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(empty_frame_response)
        metrics = result.resource_metrics[0].scope_metrics[0].metrics
        assert len(metrics) == 0

    def test_invalid_frame_is_skipped(self, invalid_frame_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(invalid_frame_response)
        metrics = result.resource_metrics[0].scope_metrics[0].metrics
        assert len(metrics) == 0


# ── JSON / OTLP wire format ───────────────────────────────────────────────────


class TestOtlpJsonFormat:
    """Verify that MessageToDict produces the camelCase keys expected by the
    OTLP JSON spec (as seen in tests/fixtures/messages.json)."""

    def test_top_level_key_is_resource_metrics(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        d = MessageToDict(result)
        assert "resourceMetrics" in d

    def test_resource_attributes_key(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(
            single_metric_response, resource_attrs={"service.name": "grafana"}
        )
        d = MessageToDict(result)
        resource = d["resourceMetrics"][0]["resource"]
        assert "attributes" in resource
        assert resource["attributes"][0]["key"] == "service.name"
        assert resource["attributes"][0]["value"]["stringValue"] == "grafana"

    def test_scope_metrics_key(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        d = MessageToDict(result)
        assert "scopeMetrics" in d["resourceMetrics"][0]

    def test_data_points_key_is_camel_case(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        d = MessageToDict(result)
        gauge = d["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["gauge"]
        assert "dataPoints" in gauge

    def test_time_unix_nano_is_string_in_json(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        # Protobuf serialises int64 as string in JSON to preserve precision.
        result = convert_grafana_resp_to_otlp(single_metric_response)
        d = MessageToDict(result)
        point = d["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["gauge"]["dataPoints"][0]
        assert isinstance(point["timeUnixNano"], str)
        assert point["timeUnixNano"] == str(1700000000000 * _MS_TO_NS)

    def test_as_double_key_in_json(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        d = MessageToDict(result)
        point = d["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["gauge"]["dataPoints"][0]
        assert "asDouble" in point
        assert point["asDouble"] == 42.0


# ── Datapoint attributes (Prometheus labels) ──────────────────────────────────


class TestDataPointAttributes:
    def test_two_frames_produce_two_data_points(
        self, labeled_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(labeled_metric_response)
        points = result.resource_metrics[0].scope_metrics[0].metrics[0].gauge.data_points
        assert len(points) == 2

    def test_first_frame_labels_propagated(
        self, labeled_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(labeled_metric_response)
        points = result.resource_metrics[0].scope_metrics[0].metrics[0].gauge.data_points
        attrs = {kv.key: kv.value.string_value for kv in points[0].attributes}
        assert attrs == {"job": "api", "env": "prod"}

    def test_second_frame_labels_propagated(
        self, labeled_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(labeled_metric_response)
        points = result.resource_metrics[0].scope_metrics[0].metrics[0].gauge.data_points
        attrs = {kv.key: kv.value.string_value for kv in points[1].attributes}
        assert attrs == {"job": "worker", "env": "prod"}

    def test_multi_frame_produces_single_metric(
        self, labeled_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(labeled_metric_response)
        metrics = result.resource_metrics[0].scope_metrics[0].metrics
        assert len(metrics) == 1

    def test_no_labels_produces_empty_attributes(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        points = result.resource_metrics[0].scope_metrics[0].metrics[0].gauge.data_points
        assert all(len(p.attributes) == 0 for p in points)

    def test_attributes_in_json_format(self, labeled_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(labeled_metric_response)
        d = MessageToDict(result)
        point = d["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["gauge"]["dataPoints"][0]
        assert "attributes" in point
        attr_map = {a["key"]: a["value"]["stringValue"] for a in point["attributes"]}
        assert attr_map["job"] == "api"
        assert attr_map["env"] == "prod"


# ── ref_id → metric name mapping ──────────────────────────────────────────────


class TestRefIdToName:
    def test_name_uses_ref_id_by_default(
        self, single_metric_response: GrafanaQueryResponse
    ) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response)
        assert result.resource_metrics[0].scope_metrics[0].metrics[0].name == "A"

    def test_name_overridden_by_string(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(
            single_metric_response, ref_id_to_name="avg_scrape_duration_seconds"
        )
        assert (
            result.resource_metrics[0].scope_metrics[0].metrics[0].name
            == "avg_scrape_duration_seconds"
        )

    def test_none_falls_back_to_ref_id(self, single_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(single_metric_response, ref_id_to_name=None)
        assert result.resource_metrics[0].scope_metrics[0].metrics[0].name == "A"

    def test_name_applied_to_all_metrics(self, multi_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(
            multi_metric_response,
            ref_id_to_name="my_metric",
        )
        names = {m.name for m in result.resource_metrics[0].scope_metrics[0].metrics}
        assert names == {"my_metric"}

    def test_none_mapping_uses_ref_ids(self, multi_metric_response: GrafanaQueryResponse) -> None:
        result = convert_grafana_resp_to_otlp(multi_metric_response, ref_id_to_name=None)
        names = {m.name for m in result.resource_metrics[0].scope_metrics[0].metrics}
        assert names == {"cpu", "mem"}
