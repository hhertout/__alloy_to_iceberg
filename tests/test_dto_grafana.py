from configs.constants import DatasourceKind
from src.client.grafana_dto import (
    GrafanaDatasource,
    GrafanaQuery,
    GrafanaQueryRequest,
    GrafanaQueryResponse,
)


class TestDatasourceKind:
    def test_enum_values(self) -> None:
        assert DatasourceKind.PROMETHEUS.value == "prometheus"
        assert DatasourceKind.LOKI.value == "loki"
        assert DatasourceKind.TEMPO.value == "tempo"


class TestGrafanaDatasource:
    def test_to_dict(self) -> None:
        ds = GrafanaDatasource(uid="abc123", type="prometheus")
        assert ds.to_dict() == {"uid": "abc123", "type": "prometheus"}


class TestGrafanaQuery:
    def test_to_dict(self) -> None:
        ds = GrafanaDatasource(uid="abc123", type="prometheus")
        query = GrafanaQuery(
            ref_id="A",
            datasource=ds,
            expr='up{job="test"}',
        )
        result = query.to_dict()

        assert result["refId"] == "A"
        assert result["expr"] == 'up{job="test"}'
        assert result["datasource"]["uid"] == "abc123"


class TestGrafanaQueryRequest:
    def test_to_dict(self) -> None:
        ds = GrafanaDatasource(uid="abc123", type="prometheus")
        query = GrafanaQuery(ref_id="A", datasource=ds, expr="up")
        request = GrafanaQueryRequest(
            queries=[query],
            from_time="1700000000000",
            to_time="1700003600000",
        )
        result = request.to_dict()

        assert result["from"] == "1700000000000"
        assert result["to"] == "1700003600000"
        assert len(result["queries"]) == 1


class TestGrafanaQueryResponse:
    def test_from_dict(self, grafana_response_sample: dict) -> None:
        response = GrafanaQueryResponse.from_dict(grafana_response_sample)

        assert "A" in response.results
        assert len(response.get_frames("A")) == 1

    def test_get_values(self, grafana_response_sample: dict) -> None:
        response = GrafanaQueryResponse.from_dict(grafana_response_sample)
        values = response.get_values("A")

        assert len(values) == 2
        assert values[1] == [42.0, 43.0]

    def test_get_frames_missing_ref_id(self, grafana_response_sample: dict) -> None:
        response = GrafanaQueryResponse.from_dict(grafana_response_sample)
        assert response.get_frames("B") == []
