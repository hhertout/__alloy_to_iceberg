import polars as pl

from src.features.base import FeaturesEngineering


class FeaturesEngineeringV1(FeaturesEngineering):
    def _get_pipes(self) -> list:
        features = [
            self.get_hour_seasonality,
            self.__alloy_rolling_mean,
            self.__alloy_rolling_p50,
        ]
        self._feature_gauge.set(len(features), attributes={"version": "v1"})

        return features

    def __alloy_rolling_mean(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rolling mean over a 5 minutes window"""
        return df.with_columns(
            pl.col(self.cols.alloy_queue_length)
            .rolling_mean_by("timestamp", window_size=self.window_size_5m)
            .alias("alloy_queue_length_mean")
        )

    def __alloy_rolling_p50(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rolling median (p50) over a 5 minutes window"""
        return df.with_columns(
            pl.col(self.cols.alloy_queue_length)
            .rolling_median_by("timestamp", window_size=self.window_size_5m)
            .alias("alloy_queue_length_p50")
        )
