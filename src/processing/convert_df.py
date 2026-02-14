import polars as pl

from src.data.grafana_dto import TimeSeriesData
from utils.logging import get_logger


def convert_dataframes(data: dict[str, TimeSeriesData]) -> dict[str, pl.DataFrame]:
    """Converts validated TimeSeriesData to Polars DataFrames.

    Filters out rows with NaN values or negative timestamps and logs
    warnings when rows are dropped.
    """
    log = get_logger("push_to_blob")
    result: dict[str, pl.DataFrame] = {}
    for query_id, ts_data in data.items():
        if ts_data.is_empty:
            log.warning(f"Query '{query_id}' returned no data. Skipping.")
            continue
        df = pl.DataFrame(
            {"timestamp": ts_data.timestamps, "value": ts_data.values},
            schema={"timestamp": pl.Int64, "value": pl.Float64},
        )
        initial_len = len(df)
        df = df.filter(pl.col("value").is_not_nan())
        df = df.filter(pl.col("timestamp") > 0)
        dropped = initial_len - len(df)
        if dropped > 0:
            log.warning(
                f"Query '{query_id}': dropped {dropped} row(s) (NaN values or negative timestamps)."
            )
        result[query_id] = df
    return result
