import polars as pl


class Processor:
    @staticmethod
    def process(df: pl.DataFrame) -> pl.DataFrame:
        """Processes the DataFrame and returns a new DataFrame."""
        # Example processing: add a new column that is the sum of all numeric columns
        df = Processor.__remove_nans(df)
        df = Processor.__remove_nulls_for(df, "loki_request_rate")
        df = Processor.__remove_nulls_for(df, "alloy_queue_length")
        return df

    @staticmethod
    def __remove_nans(df: pl.DataFrame) -> pl.DataFrame:
        """Removes rows with NaN values."""
        return df.drop_nans()

    @staticmethod
    def __remove_nulls_for(df: pl.DataFrame, col: str, replace_value: float = 0.0) -> pl.DataFrame:
        """Replaces null values in the specified column with a default value (0 by default)."""
        return df.with_columns(pl.col(col).fill_null(replace_value))

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
