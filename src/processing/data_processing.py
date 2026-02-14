import polars as pl

from utils.logging import get_logger
from utils.queries import get_queries_id
from utils.telemetry import get_default_attributes, get_meter


class Processor:
    @staticmethod
    def process(df: pl.DataFrame) -> pl.DataFrame:
        """
        Processes the DataFrame and returns a new DataFrame.
        Handle missing data based on data source semantics:

            1. alloy_queue_length:
            - NULL = Scraping failure or Prometheus down
            - Action: DROP timestamp (unreliable data point)

            2. loki_request_rate:
            - NULL = No logs matched the query
            - Action: Fill with 0 (no logs = 0 occurrences)
        """
        # init
        initial_count = df.height
        _meter = get_meter("ml_obs.pipeline")
        _pipeline_runs = _meter.create_counter(
            "ml.processed.filtered_rows",
            description="Number of filtered rows",
        )

        cols = get_queries_id()

        # process
        df = (
            df.pipe(Processor.__remove_nans)
            .pipe(Processor.__filter_nulls_for, cols.alloy_queue_length)
            .pipe(Processor.__fill_nulls_for, cols.loki_request_rate)
        )

        # post process
        filtered_count = initial_count - df.height
        _pipeline_runs.add(filtered_count, attributes=get_default_attributes())

        return df

    @staticmethod
    def __remove_nans(df: pl.DataFrame) -> pl.DataFrame:
        """Removes rows with NaN values."""
        return df.drop_nans()

    @staticmethod
    def __fill_nulls_for(df: pl.DataFrame, col: str, replace_value: float = 0.0) -> pl.DataFrame:
        """Replaces null values in the specified column with a default value (0 by default)."""
        return df.with_columns(pl.col(col).fill_null(replace_value))

    @staticmethod
    def __filter_nulls_for(df: pl.DataFrame, col: str) -> pl.DataFrame:
        """Drops rows where the specified column is null."""
        # Telemetry: Count the number of dropped rows due to null values in the specified column
        _meter = get_meter("ml_obs.pipeline")
        _pipeline_runs = _meter.create_counter(
            "ml.processed.dropped_rows",
            description="Number of dropped rows due to null values in critical columns",
        )

        initial_count = df.height
        df = df.filter(pl.col(col).is_not_null())
        filtered_count = initial_count - df.height

        _pipeline_runs.add(filtered_count, attributes={**get_default_attributes(), "column": col})
        if filtered_count > 0:
            log = get_logger("push_to_blob")
            log.warning(f"Dropped {filtered_count} rows due to null values in column '{col}'")

        return df

    @staticmethod
    def is_null_present(df: pl.DataFrame) -> bool:
        """Checks if there are any null values in the DataFrame."""
        return bool(df.null_count().select(pl.sum_horizontal(pl.all())).item() > 0)

    @staticmethod
    def is_nan_present(df: pl.DataFrame) -> bool:
        """Checks if there are any NaN values in the DataFrame."""
        nan_check = df.select(pl.col(pl.Float64).is_nan().any())
        if nan_check.width == 0:
            return False
        return bool(nan_check.select(pl.any_horizontal(pl.all())).item())
