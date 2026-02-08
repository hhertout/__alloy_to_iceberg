
import polars as pl
import pytest

from scripts.push_to_blob import (
    convert_dataframes,
    extract_loki_queries,
    extract_promtheus_queries,
    merge_dataframes,
    process_data,
)
from src.data.grafana_dto import TimeSeriesData

# ── extract_*_queries ──


class TestExtractQueries:
    def test_extract_prometheus_queries(self) -> None:
        cfg = {"prometheus": {"ds1": [{"id": "a", "query": "up"}]}}
        assert extract_promtheus_queries(cfg) == {"ds1": [{"id": "a", "query": "up"}]}

    def test_extract_prometheus_queries_missing_key(self) -> None:
        assert extract_promtheus_queries({}) == []

    def test_extract_loki_queries(self) -> None:
        cfg = {"loki": {"ds2": [{"id": "b", "query": "{app='x'}"}]}}
        assert extract_loki_queries(cfg) == {"ds2": [{"id": "b", "query": "{app='x'}"}]}

    def test_extract_loki_queries_missing_key(self) -> None:
        assert extract_loki_queries({}) == []


# ── convert_dataframes ──


class TestConvertDataframes:
    def test_basic_conversion(self) -> None:
        data = {
            "cpu": TimeSeriesData(
                query_id="cpu",
                timestamps=[1000, 2000, 3000],
                values=[0.1, 0.2, 0.3],
            )
        }
        result = convert_dataframes(data)

        assert "cpu" in result
        df = result["cpu"]
        assert df.shape == (3, 2)
        assert df.schema == {"timestamp": pl.Int64, "value": pl.Float64}

    def test_empty_series_skipped(self) -> None:
        data = {
            "empty": TimeSeriesData(query_id="empty", timestamps=[], values=[]),
            "ok": TimeSeriesData(query_id="ok", timestamps=[1000], values=[1.0]),
        }
        result = convert_dataframes(data)

        assert "empty" not in result
        assert "ok" in result

    def test_nan_values_filtered(self) -> None:
        data = {
            "q": TimeSeriesData(
                query_id="q",
                timestamps=[1000, 2000, 3000],
                values=[1.0, float("nan"), 3.0],
            )
        }
        result = convert_dataframes(data)
        df = result["q"]

        assert len(df) == 2
        assert df["value"].to_list() == [1.0, 3.0]

    def test_negative_timestamps_filtered(self) -> None:
        data = {
            "q": TimeSeriesData(
                query_id="q",
                timestamps=[-1, 0, 1000],
                values=[1.0, 2.0, 3.0],
            )
        }
        result = convert_dataframes(data)
        df = result["q"]

        assert len(df) == 1
        assert df["timestamp"].to_list() == [1000]

    def test_nan_and_negative_combined(self) -> None:
        data = {
            "q": TimeSeriesData(
                query_id="q",
                timestamps=[-1, 2000, 3000, 0],
                values=[1.0, float("nan"), 3.0, 4.0],
            )
        }
        result = convert_dataframes(data)
        df = result["q"]

        assert len(df) == 1
        assert df["timestamp"].to_list() == [3000]
        assert df["value"].to_list() == [3.0]

    def test_all_rows_filtered_returns_empty_df(self) -> None:
        data = {
            "q": TimeSeriesData(
                query_id="q",
                timestamps=[-1],
                values=[float("nan")],
            )
        }
        result = convert_dataframes(data)
        assert len(result["q"]) == 0


# ── merge_dataframes ──


class TestMergeDataframes:
    def test_single_dataframe(self) -> None:
        data = {
            "cpu": pl.DataFrame(
                {"timestamp": [1000, 2000], "value": [0.1, 0.2]},
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            )
        }
        result = merge_dataframes(data)

        assert "cpu" in result.columns
        assert "timestamp" in result.columns
        assert result.shape == (2, 2)

    def test_exact_timestamp_match(self) -> None:
        data = {
            "cpu": pl.DataFrame(
                {"timestamp": [1000, 2000], "value": [0.1, 0.2]},
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            ),
            "mem": pl.DataFrame(
                {"timestamp": [1000, 2000], "value": [0.5, 0.6]},
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            ),
        }
        result = merge_dataframes(data)

        assert result.shape == (2, 3)
        assert set(result.columns) == {"timestamp", "cpu", "mem"}

    def test_asof_join_within_tolerance(self) -> None:
        """Timestamps within 15s (15000ms) should be matched."""
        data = {
            "cpu": pl.DataFrame(
                {"timestamp": [1_000_000], "value": [0.1]},
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            ),
            "mem": pl.DataFrame(
                {"timestamp": [1_010_000], "value": [0.5]},  # 10s offset
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            ),
        }
        result = merge_dataframes(data)

        assert result.shape == (1, 3)
        assert result["mem"][0] == pytest.approx(0.5)

    def test_asof_join_outside_tolerance(self) -> None:
        """Timestamps > 15s apart should produce null."""
        data = {
            "cpu": pl.DataFrame(
                {"timestamp": [1_000_000], "value": [0.1]},
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            ),
            "mem": pl.DataFrame(
                {"timestamp": [1_020_000], "value": [0.5]},  # 20s offset
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            ),
        }
        result = merge_dataframes(data)

        assert result.shape == (1, 3)
        assert result["mem"][0] is None

    def test_empty_dict(self) -> None:
        result = merge_dataframes({})
        assert result.shape == (0, 0)

    def test_unsorted_input_gets_sorted(self) -> None:
        data = {
            "cpu": pl.DataFrame(
                {"timestamp": [3000, 1000, 2000], "value": [0.3, 0.1, 0.2]},
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            ),
            "mem": pl.DataFrame(
                {"timestamp": [2000, 3000, 1000], "value": [0.6, 0.7, 0.5]},
                schema={"timestamp": pl.Int64, "value": pl.Float64},
            ),
        }
        result = merge_dataframes(data)

        assert result["timestamp"].to_list() == [1000, 2000, 3000]
        assert result["mem"].to_list() == [0.5, 0.6, 0.7]


# ── process_data ──


class TestProcessData:
    def test_sanitize_result_is_used(self) -> None:
        """Verify process() receives the output of sanitize(), not the original."""

        class DropNullProcessor:
            def sanitize(self, df: pl.DataFrame) -> pl.DataFrame:
                return df.drop_nulls()

            def process(self, df: pl.DataFrame) -> pl.DataFrame:
                return df

        df = pl.DataFrame({"a": [1, None, 3]})
        result = process_data(DropNullProcessor(), df)

        assert len(result) == 2
        assert result["a"].to_list() == [1, 3]
