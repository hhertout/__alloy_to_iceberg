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
            self.hour_seasonality,
            self.harmonics_temporality_hours,
            self.business_day_seasonality,
            self._v1_features,
        ]
        self._feature_gauge.set(len(features), attributes={"version": "v1"})

        return features

    def _v1_features(self, df: pl.DataFrame) -> pl.DataFrame:
        lag_cols = [self.cols.alloy_queue_length, self.cols.cpu_usage, self.cols.loki_request_rate]
        rolling_cols = [
            self.cols.alloy_queue_length,
            self.cols.cpu_usage,
            self.cols.loki_request_rate,
        ]
        diff_ratio_cols = [col for col in rolling_cols if col != self.cols.alloy_queue_length]

        df = self.__lag(df, lag_cols, minutes=1, suffix="1m")
        df = self.__lag(df, lag_cols, minutes=2, suffix="2m")
        df = self.__lag(df, lag_cols, minutes=5, suffix="5m")
        df = self.__lag(df, lag_cols, minutes=10, suffix="10m")
        df = self.__lag(df, lag_cols, minutes=30, suffix="30m")
        df = self.__lag(df, lag_cols, minutes=60, suffix="1h")
        df = self.__lag(df, lag_cols, minutes=720, suffix="12h")
        df = self.__lag(df, lag_cols, minutes=1440, suffix="1d")
        df = self.__lag(df, lag_cols, minutes=10080, suffix="7d")
        df = self.__lag(df, lag_cols, minutes=21600, suffix="15d")
        df = self.__lag(df, lag_cols, minutes=43200, suffix="30d")

        df = self.__rolling_mean(df, rolling_cols, self.window_size_5m)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_10m)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_30m)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_1h)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_6h)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_12h)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_1d)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_7d)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_15d)
        df = self.__rolling_mean(df, rolling_cols, self.window_size_30d)

        df = self.__diff_ratio(df, diff_ratio_cols)

        df = self.__rolling_std(df, rolling_cols, self.window_size_5m)
        df = self.__rolling_std(df, rolling_cols, self.window_size_10m)
        df = self.__rolling_std(df, rolling_cols, self.window_size_30m)
        df = self.__rolling_std(df, rolling_cols, self.window_size_1h)
        df = self.__rolling_std(df, rolling_cols, self.window_size_6h)
        df = self.__rolling_std(df, rolling_cols, self.window_size_12h)
        df = self.__rolling_std(df, rolling_cols, self.window_size_1d)
        df = self.__rolling_std(df, rolling_cols, self.window_size_7d)
        df = self.__rolling_std(df, rolling_cols, self.window_size_15d)
        df = self.__rolling_std(df, rolling_cols, self.window_size_30d)

        df = self.__delta_zscore(df, diff_ratio_cols)

        # df = self.__rolling_p50(df, percentile_cols, self.window_size_5m)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_10m)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_30m)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_1h)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_6h)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_12h)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_1d)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_7d)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_15d)
        # df = self.__rolling_p50(df, percentile_cols, self.window_size_30d)

        # df = self.__rolling_p90(df, percentile_cols, self.window_size_5m)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_10m)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_30m)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_1h)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_6h)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_12h)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_1d)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_7d)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_15d)
        # df = self.__rolling_p90(df, percentile_cols, self.window_size_30d)

        return df

    def __rolling_mean(self, df: pl.DataFrame, cols: list[str], window_size: str) -> pl.DataFrame:
        for col in cols:
            df = df.with_columns(
                pl.col(col)
                .rolling_mean_by("timestamp", window_size=window_size)
                .shift(1)
                .alias(f"{col}_mean_{window_size}")
            )
        return df

    def __rolling_std(self, df: pl.DataFrame, cols: list[str], window_size: str) -> pl.DataFrame:
        for col in cols:
            df = df.with_columns(
                pl.col(col)
                .rolling_std_by("timestamp", window_size=window_size)
                .shift(1)
                .alias(f"{col}_std_{window_size}")
            )
        return df

    def __diff_ratio(self, df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
        eps = 1e-9
        for col in cols:
            mean_1h_col = f"{col}_mean_{self.window_size_1h}"
            mean_1d_col = f"{col}_mean_{self.window_size_1d}"

            df = df.with_columns(
                (pl.col(col).shift(1) - pl.col(mean_1h_col)).alias(f"{col}_diff_mean_1h")
            )
            df = df.with_columns(
                pl.when(pl.col(mean_1d_col).abs() > eps)
                .then(pl.col(mean_1h_col) / pl.col(mean_1d_col))
                .otherwise(None)
                .alias(f"{col}_ratio_mean_1h_1d")
            )
        return df

    def __delta_zscore(self, df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
        eps = 1e-9
        for col in cols:
            mean_1h_col = f"{col}_mean_{self.window_size_1h}"
            std_1h_col = f"{col}_std_{self.window_size_1h}"
            mean_1d_col = f"{col}_mean_{self.window_size_1d}"
            std_1d_col = f"{col}_std_{self.window_size_1d}"

            df = df.with_columns(
                (pl.col(mean_1h_col) - pl.col(mean_1h_col).shift(1)).alias(f"{col}_delta_mean_1h")
            )

            df = df.with_columns(
                pl.when(pl.col(std_1h_col).abs() > eps)
                .then((pl.col(col).shift(1) - pl.col(mean_1h_col)) / pl.col(std_1h_col))
                .otherwise(None)
                .alias(f"{col}_zscore_1h")
            )

            df = df.with_columns(
                pl.when(pl.col(std_1d_col).abs() > eps)
                .then((pl.col(col).shift(1) - pl.col(mean_1d_col)) / pl.col(std_1d_col))
                .otherwise(None)
                .alias(f"{col}_zscore_1d")
            )

        return df

    def __lag(self, df: pl.DataFrame, cols: list[str], minutes: int, suffix: str) -> pl.DataFrame:
        shift_ratio_min = int(60 / self.index_size)
        shift_steps = minutes * shift_ratio_min
        for col in cols:
            df = df.with_columns(pl.col(col).shift(shift_steps).alias(f"{col}_lag_{suffix}"))
        return df

    def __rolling_p50(self, df: pl.DataFrame, cols: list[str], window_size: str) -> pl.DataFrame:
        for col in cols:
            df = df.with_columns(
                pl.col(col)
                .rolling_median_by("timestamp", window_size=window_size)
                .shift(1)
                .alias(f"{col}_p50_{window_size}")
            )
        return df

    def __rolling_p90(self, df: pl.DataFrame, cols: list[str], window_size: str) -> pl.DataFrame:
        for col in cols:
            df = df.with_columns(
                pl.col(col)
                .rolling_quantile_by("timestamp", quantile=0.9, window_size=window_size)
                .shift(1)
                .alias(f"{col}_p90_{window_size}")
            )
        return df
