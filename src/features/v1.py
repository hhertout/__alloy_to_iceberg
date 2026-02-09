import polars as pl

from configs.get_queries_id import get_queries_id


class FeaturesEngineeringV1:
    """
    This class is responsible for engineering features from the raw data.
    It includes methods for feature extraction, transformation, and selection.
    """

    def __init__(self):
        self.cols = get_queries_id()
        self.window_size_5m = "300000i"  # in ms, so 5min = 5*60*1000ms

    def genrate_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Generates features from the input DataFrame."""
        df = df.pipe(self.__generate_alloy_mean).pipe(self.__generate_alloy_p50)

        return df

    def __generate_alloy_mean(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            pl.col(self.cols.alloy_queue_length)
            .rolling_mean_by("timestamp", window_size=self.window_size_5m)
            .alias("alloy_queue_length_mean")
        )

    def __generate_alloy_p50(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            pl.col(self.cols.alloy_queue_length)
            .rolling_median_by("timestamp", window_size=self.window_size_5m)
            .alias("alloy_queue_length_p50")
        )
