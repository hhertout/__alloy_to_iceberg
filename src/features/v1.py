import polars as pl

from src.features.base import FeaturesEngineering


class FeaturesEngineeringV1(FeaturesEngineering):
    def _get_pipes(self) -> list:
        # To add:
        # - short lag : t-1, t-5, t-15
        # - delta rates: x_t - x_t-1
        # - rolling stats: mean, p50, p90 over 5min, 10min windows
        # - Z-score normalization -> (x-mean_rolling)/std_rolling
        # - rolling quantiles: p50, p90 over 5min, 10min windows
        features = [
            self.get_hour_seasonality,
            self.__alloy_rolling_mean,
            self.__alloy_rolling_p50,
            self.__cpu_rolling_mean,
            self.__cpu_rolling_p50,
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
    
    def __cpu_rolling_mean(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rolling mean over a 5 minutes window"""
        return df.with_columns(
            pl.col(self.cols.cpu_usage)
            .rolling_mean_by("timestamp", window_size=self.window_size_5m)
            .alias("cpu_usage_mean")
        )

    def __cpu_rolling_p50(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rolling median (p50) over a 5 minutes window"""
        return df.with_columns(
            pl.col(self.cols.cpu_usage)
            .rolling_median_by("timestamp", window_size=self.window_size_5m)
            .alias("cpu_usage_p50")
        )
