import polars as pl
import pytest

from src.data.grafana_dto import TimeSeriesData
from src.processing.merge_dataframes import (
    _get_agg_expr,
    _get_clean_dataframes,
    _to_agg_dataframe,
    merge_dataframes,
)

# ── helpers ──


class _MockMetric:
    """Minimal stub for the OTel metric passed to merge_dataframes."""

    def __init__(self) -> None:
        self.last_value: int | None = None

    def add(self, value: int, **kwargs: object) -> None:
        self.last_value = value

    def set(self, value: int, **kwargs: object) -> None:
        self.last_value = value


# ── _get_clean_dataframes ──


class TestGetCleanDataframes:
    def test_single_timeseries(self) -> None:
        data = {
            "cpu": TimeSeriesData(
                query_id="cpu", timestamps=[3000, 1000], values=[0.3, 0.1], agg="mean"
            ),
        }
        dfs, agg_map = _get_clean_dataframes(data)

        assert len(dfs) == 1
        assert agg_map == {"cpu": "mean"}
        # Should be sorted by timestamp
        assert dfs[0]["timestamp"].to_list() == [1000, 3000]
        assert dfs[0]["cpu"].to_list() == [pytest.approx(0.1), pytest.approx(0.3)]

    def test_multiple_timeseries(self) -> None:
        data = {
            "cpu": TimeSeriesData(query_id="cpu", timestamps=[1000], values=[0.1], agg="mean"),
            "logs": TimeSeriesData(query_id="logs", timestamps=[2000], values=[5.0], agg="sum"),
        }
        dfs, agg_map = _get_clean_dataframes(data)

        assert len(dfs) == 2
        assert agg_map == {"cpu": "mean", "logs": "sum"}

    def test_empty_data(self) -> None:
        dfs, agg_map = _get_clean_dataframes({})

        assert dfs == []
        assert agg_map == {}

    def test_schema_types(self) -> None:
        data = {
            "m": TimeSeriesData(query_id="m", timestamps=[1000], values=[42.0], agg="last"),
        }
        dfs, _ = _get_clean_dataframes(data)

        assert dfs[0].schema["timestamp"] == pl.Int64
        assert dfs[0].schema["m"] == pl.Float64


# ── _get_agg_expr ──


class TestGetAggExpr:
    def test_mean(self) -> None:
        exprs = _get_agg_expr({"cpu": "mean"})
        assert len(exprs) == 1

    def test_sum(self) -> None:
        exprs = _get_agg_expr({"logs": "sum"})
        assert len(exprs) == 1

    def test_all_supported_aggs(self) -> None:
        agg_map = {
            "a": "mean",
            "b": "sum",
            "c": "min",
            "d": "max",
            "e": "first",
            "f": "last",
        }
        exprs = _get_agg_expr(agg_map)
        assert len(exprs) == 6

    def test_unknown_agg_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown aggregation 'median'"):
            _get_agg_expr({"bad": "median"})

    def test_empty_map(self) -> None:
        assert _get_agg_expr({}) == []


# ── _to_agg_dataframe ──


class TestToAggDataframe:
    def test_single_window_mean(self) -> None:
        """Two points in the same 60s window → aggregated to one row."""
        df = pl.DataFrame(
            {"timestamp": [960_000, 980_000], "val": [0.1, 0.3]},
            schema={"timestamp": pl.Int64, "val": pl.Float64},
        )
        exprs = [pl.col("val").mean()]
        result = _to_agg_dataframe(df, exprs)

        assert result.height == 1
        assert result["val"][0] == pytest.approx(0.2)

    def test_two_windows(self) -> None:
        """Points 60s apart → two separate windows."""
        df = pl.DataFrame(
            {"timestamp": [1_000_000, 1_060_000], "val": [0.1, 0.5]},
            schema={"timestamp": pl.Int64, "val": pl.Float64},
        )
        exprs = [pl.col("val").mean()]
        result = _to_agg_dataframe(df, exprs)

        assert result.height == 2
        assert result["val"][0] == pytest.approx(0.1)
        assert result["val"][1] == pytest.approx(0.5)

    def test_sum_aggregation(self) -> None:
        df = pl.DataFrame(
            {"timestamp": [960_000, 980_000, 1_000_000], "cnt": [1.0, 2.0, 3.0]},
            schema={"timestamp": pl.Int64, "cnt": pl.Float64},
        )
        exprs = [pl.col("cnt").sum()]
        result = _to_agg_dataframe(df, exprs)

        assert result.height == 1
        assert result["cnt"][0] == pytest.approx(6.0)

    def test_multiple_columns(self) -> None:
        df = pl.DataFrame(
            {
                "timestamp": [960_000, 980_000],
                "cpu": [0.2, 0.4],
                "logs": [3.0, 7.0],
            },
            schema={"timestamp": pl.Int64, "cpu": pl.Float64, "logs": pl.Float64},
        )
        exprs = [pl.col("cpu").mean(), pl.col("logs").sum()]
        result = _to_agg_dataframe(df, exprs)

        assert result.height == 1
        assert result["cpu"][0] == pytest.approx(0.3)
        assert result["logs"][0] == pytest.approx(10.0)


# ── merge_dataframes (integration) ──


class TestMergeDataframesIntegration:
    def test_metric_counter_updated(self) -> None:
        """The OTel metric should be called with the row count."""
        metric = _MockMetric()
        data = {
            "cpu": TimeSeriesData(
                query_id="cpu", timestamps=[1000, 2000], values=[0.1, 0.2], agg="mean"
            ),
        }
        result = merge_dataframes(data, metric=metric)

        assert metric.last_value == result.height

    def test_mixed_agg_strategies(self) -> None:
        """mean + sum used in the same merge."""
        metric = _MockMetric()
        data = {
            "gauge": TimeSeriesData(
                query_id="gauge",
                timestamps=[960_000, 980_000],
                values=[10.0, 20.0],
                agg="mean",
            ),
            "counter": TimeSeriesData(
                query_id="counter",
                timestamps=[960_000, 980_000],
                values=[1.0, 4.0],
                agg="sum",
            ),
        }
        result = merge_dataframes(data, metric=metric)

        assert result["gauge"][0] == pytest.approx(15.0)
        assert result["counter"][0] == pytest.approx(5.0)

    def test_left_join_preserves_all_timestamps(self) -> None:
        """Sources with non-overlapping timestamps should both appear."""
        metric = _MockMetric()
        data = {
            "a": TimeSeriesData(query_id="a", timestamps=[1_000_000], values=[1.0], agg="mean"),
            "b": TimeSeriesData(query_id="b", timestamps=[2_000_000], values=[2.0], agg="mean"),
        }
        result = merge_dataframes(data, metric=metric)

        # Two separate windows, each with its own metric
        assert result.height == 2
        assert result.filter(pl.col("a").is_not_null()).height >= 1
        assert result.filter(pl.col("b").is_not_null()).height >= 1

    def test_single_dataframe(self) -> None:
        metric = _MockMetric()
        data = {
            "cpu": TimeSeriesData(
                query_id="cpu", timestamps=[1000, 2000], values=[0.1, 0.2], agg="mean"
            ),
        }
        result = merge_dataframes(data, metric=metric)

        assert "cpu" in result.columns
        assert "timestamp" in result.columns

    def test_exact_timestamp_match(self) -> None:
        metric = _MockMetric()
        data = {
            "cpu": TimeSeriesData(
                query_id="cpu", timestamps=[1000, 2000], values=[0.1, 0.2], agg="mean"
            ),
            "mem": TimeSeriesData(
                query_id="mem", timestamps=[1000, 2000], values=[0.5, 0.6], agg="mean"
            ),
        }
        result = merge_dataframes(data, metric=metric)

        assert set(result.columns) == {"timestamp", "cpu", "mem"}

    def test_resampling_aggregates_mean(self) -> None:
        """Two points in the same 60s window should be averaged."""
        metric = _MockMetric()
        data = {
            "cpu": TimeSeriesData(
                query_id="cpu",
                timestamps=[960_000, 990_000, 1_020_000],
                values=[0.1, 0.3, 0.5],
                agg="mean",
            ),
        }
        result = merge_dataframes(data, metric=metric)

        # First window [960000, 1020000) contains 0.1 and 0.3 → mean 0.2
        # Second window [1020000, 1080000) contains 0.5
        assert result.height >= 2
        assert result["cpu"][0] == pytest.approx(0.2)
        assert result["cpu"][1] == pytest.approx(0.5)

    def test_resampling_aggregates_sum(self) -> None:
        """Sum agg should add values in the same window."""
        metric = _MockMetric()
        data = {
            "logs": TimeSeriesData(
                query_id="logs",
                timestamps=[960_000, 990_000],
                values=[4.0, 6.0],
                agg="sum",
            ),
        }
        result = merge_dataframes(data, metric=metric)

        # Both points fall in [960000, 1020000) → sum = 10.0
        assert result["logs"][0] == pytest.approx(10.0)

    def test_no_data_lost_different_frequencies(self) -> None:
        """Data points far apart should end up in different windows."""
        metric = _MockMetric()
        data = {
            "prom": TimeSeriesData(
                query_id="prom", timestamps=[1000, 2000, 3000], values=[1.0, 2.0, 3.0], agg="mean"
            ),
            "loki": TimeSeriesData(
                query_id="loki", timestamps=[1500, 120_000], values=[10.0, 50.0], agg="sum"
            ),
        }
        result = merge_dataframes(data, metric=metric)

        assert set(result.columns) == {"timestamp", "prom", "loki"}
        # loki@120_000 must be present (in a separate window)
        assert result.filter(pl.col("loki") == 50.0).height == 1

    def test_empty_dict(self) -> None:
        metric = _MockMetric()
        result = merge_dataframes({}, metric=metric)
        assert result.shape == (0, 0)

    def test_unsorted_input_gets_sorted(self) -> None:
        metric = _MockMetric()
        data = {
            "cpu": TimeSeriesData(
                query_id="cpu", timestamps=[3000, 1000, 2000], values=[0.3, 0.1, 0.2], agg="mean"
            ),
            "mem": TimeSeriesData(
                query_id="mem", timestamps=[2000, 3000, 1000], values=[0.6, 0.7, 0.5], agg="mean"
            ),
        }
        result = merge_dataframes(data, metric=metric)

        assert result["timestamp"].to_list() == sorted(result["timestamp"].to_list())

    def test_unknown_agg_raises(self) -> None:
        metric = _MockMetric()
        data = {
            "bad": TimeSeriesData(query_id="bad", timestamps=[1000], values=[1.0], agg="median"),
        }
        with pytest.raises(ValueError, match="Unknown aggregation"):
            merge_dataframes(data, metric=metric)
