import polars as pl
from opentelemetry.metrics import UpDownCounter

from configs.constants import DEFAULT_AGG_INTERVAL_MS
from src.data.grafana_dto import TimeSeriesData
from utils.telemetry import get_default_attributes


def merge_dataframes(data: dict[str, TimeSeriesData], metric: UpDownCounter) -> pl.DataFrame:
    """Merges multiple single-metric DataFrames into one wide DataFrame.

    Builds a complete timeline from every source's timestamps, joins each
    metric with a left join, then resamples to a regular interval using
    the aggregation strategy defined per-query in the YAML config.
    """
    if not data:
        return pl.DataFrame()

    dfs, agg_map = _get_clean_dataframes(data)

    # Prefill the new df with all unique timestamps available
    all_timestamps = pl.concat([df.select("timestamp") for df in dfs]).unique().sort("timestamp")
    merged_df = all_timestamps
    for df in dfs:
        merged_df = merged_df.join(df, on="timestamp", how="left")

    agg_exprs = _get_agg_expr(agg_map)
    merged_df = _to_agg_dataframe(merged_df, agg_exprs)

    metric.add(len(merged_df), attributes=get_default_attributes())
    return merged_df


def _get_clean_dataframes(
    data: dict[str, TimeSeriesData],
) -> tuple[list[pl.DataFrame], dict[str, str]]:
    dfs: list[pl.DataFrame] = []
    agg_map: dict[str, str] = {}
    for query_id, ts_data in data.items():
        df = pl.DataFrame(
            {"timestamp": ts_data.timestamps, query_id: [float(v) for v in ts_data.values]},
            schema={"timestamp": pl.Int64, query_id: pl.Float64},
        ).sort("timestamp")
        dfs.append(df)
        agg_map[query_id] = ts_data.agg

    return dfs, agg_map


def _get_agg_expr(agg_map: dict[str, str]) -> list[pl.Expr]:
    _agg_dispatch = {
        "mean": lambda c: pl.col(c).mean(),
        "sum": lambda c: pl.col(c).sum(),
        "min": lambda c: pl.col(c).min(),
        "max": lambda c: pl.col(c).max(),
        "first": lambda c: pl.col(c).first(),
        "last": lambda c: pl.col(c).last(),
    }

    agg_exprs = []
    for col_name, agg_name in agg_map.items():
        builder = _agg_dispatch.get(agg_name)
        if builder is None:
            raise ValueError(f"Unknown aggregation '{agg_name}' for column '{col_name}'")
        agg_exprs.append(builder(col_name))

    return agg_exprs


def _to_agg_dataframe(df: pl.DataFrame, agg_exprs: list[pl.Expr]) -> pl.DataFrame:
    return df.group_by_dynamic("timestamp", every=f"{DEFAULT_AGG_INTERVAL_MS}i").agg(agg_exprs)
