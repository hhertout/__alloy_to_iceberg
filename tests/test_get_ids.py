from types import SimpleNamespace
from unittest.mock import mock_open, patch

import pytest
import yaml

from utils.queries import get_queries_id

SINGLE_DS_CONFIG = {
    "prometheus": {
        "Mimir": [
            {"id": "alloy_queue_length", "agg": "mean", "query": "sum(...)"},
        ]
    }
}

MULTI_DS_CONFIG = {
    "prometheus": {
        "Mimir": [
            {"id": "alloy_queue_length", "agg": "mean", "query": "sum(...)"},
        ]
    },
    "loki": {
        "Loki": [
            {"id": "loki_request_rate", "agg": "mean", "query": "count_over_time(...)"},
        ]
    },
}

MULTI_QUERIES_CONFIG = {
    "prometheus": {
        "Mimir": [
            {"id": "col_a", "agg": "mean", "query": "q1"},
            {"id": "col_b", "agg": "sum", "query": "q2"},
            {"id": "col_c", "agg": "max", "query": "q3"},
        ]
    },
}


def _mock_config(config: dict):
    return patch("builtins.open", mock_open(read_data=yaml.dump(config)))


class TestGetColsFromConfig:
    def test_returns_simple_namespace(self) -> None:
        with _mock_config(SINGLE_DS_CONFIG):
            result = get_queries_id()
        assert isinstance(result, SimpleNamespace)

    def test_single_datasource(self) -> None:
        with _mock_config(SINGLE_DS_CONFIG):
            cols = get_queries_id()
        assert cols.alloy_queue_length == "alloy_queue_length"

    def test_multiple_datasources(self) -> None:
        with _mock_config(MULTI_DS_CONFIG):
            cols = get_queries_id()
        assert cols.alloy_queue_length == "alloy_queue_length"
        assert cols.loki_request_rate == "loki_request_rate"

    def test_multiple_queries_per_datasource(self) -> None:
        with _mock_config(MULTI_QUERIES_CONFIG):
            cols = get_queries_id()
        assert cols.col_a == "col_a"
        assert cols.col_b == "col_b"
        assert cols.col_c == "col_c"

    def test_attribute_count_matches_query_count(self) -> None:
        with _mock_config(MULTI_QUERIES_CONFIG):
            cols = get_queries_id()
        assert len(vars(cols)) == 3

    def test_typo_raises_attribute_error(self) -> None:
        with _mock_config(SINGLE_DS_CONFIG):
            cols = get_queries_id()
        with pytest.raises(AttributeError):
            _ = cols.alloy_queu_length  # typo

    def test_empty_config(self) -> None:
        with _mock_config({}):
            cols = get_queries_id()
        assert len(vars(cols)) == 0
