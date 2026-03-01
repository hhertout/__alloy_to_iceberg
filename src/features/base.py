from abc import ABC, abstractmethod

import numpy as np
import polars as pl

from configs.constants import DEFAULT_AGG_INTERVAL_MS
from utils.queries import get_queries_id
from utils.telemetry import get_meter


class FeaturesEngineering(ABC):
    """
    Base class for feature engineering.
    Subclasses define their own pipeline via `_get_pipes()`.
    Common features shared across versions live here.
    """

    def __init__(self) -> None:
        self.cols = get_queries_id()
        self.index_size = DEFAULT_AGG_INTERVAL_MS / 1000  # in seconds
        self.window_size_5m = "300000i"  # in ms, so 5min = 5*60*1000ms
        self.window_size_10m = "600000i"  # in ms, so 10min = 10*60*1000ms
        self.window_size_30m = "1800000i"  # in ms, so 30min = 30*60*1000ms
        self.window_size_1h = "3600000i"  # in ms, so 1h = 60*60*1000ms
        self.window_size_6h = "21600000i"  # in ms, so 6h = 6*60*60*1000ms
        self.window_size_12h = "43200000i"  # in ms, so 12h = 12*60*60*1000ms
        self.window_size_1d = "86400000i"  # in ms, so 1d = 24*60*60*1000ms
        self.window_size_2d = "172800000i"  # in ms, so 2d = 2*24*60*60*1000ms
        self.window_size_3d = "259200000i"  # in ms, so 3d = 3*24*60*60*1000ms
        self.window_size_7d = "604800000i"  # in ms, so 7d = 7*24*60*60*1000ms
        self.window_size_15d = "1296000000i"  # in ms, so 15d = 15*24*60*60*1000ms
        self.window_size_30d = "2592000000i"  # in ms, so 30d = 30*24*60*60*1000ms

        self._meter = get_meter("ml_obs.pipeline")

        self._feature_gauge = self._meter.create_gauge(
            "ml.features.number",
            description="Number of features generated after applying the feature engineering pipeline.",
        )

    @abstractmethod
    def _get_ml_pipes(self) -> list:
        """Return the ordered list of ML pipe functions for this version."""
        ...

    @abstractmethod
    def _get_torch_pipes(self) -> list:
        """Return the ordered list of Torch pipe functions for this version."""
        ...

    def generate_ml_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Applies all ML pipes sequentially."""
        for pipe in self._get_ml_pipes():
            df = df.pipe(pipe)
        return df

    def generate_torch_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Applies all Torch pipes sequentially."""
        for pipe in self._get_torch_pipes():
            df = df.pipe(pipe)
        return df

    # -- Common features (shared across versions) --
    # Empty for now, but this is where we would add any features that are common to all versions of the pipeline.

    def hour_seasonality(self, df: pl.DataFrame) -> pl.DataFrame:
        # Convert integer epoch milliseconds to Datetime before extracting hour.
        return (
            df.with_columns(hour=pl.col("timestamp").cast(pl.Datetime("ms")).dt.hour())
            .with_columns(hour_radian=2 * np.pi * pl.col("hour") / 24)
            .with_columns(
                hour_sin=pl.col("hour_radian").sin(),
                hour_cos=pl.col("hour_radian").cos(),
            )
            .drop("hour_radian")
            .drop("hour")
        )

    def harmonics_temporality_hours(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Adds harmonic features for the hour of the day to capture complex seasonal patterns.
        For each harmonic, we create sine and cosine features to allow the model to learn both amplitude and phase shifts in the daily seasonality.
        The number of harmonics can be tuned; here we use 3 as a common choice to capture up to the third harmonic of daily seasonality.
        """

        HARMONIC_SERIES = 3
        for h in range(1, HARMONIC_SERIES + 1):
            df = (
                df.with_columns(pl.col("timestamp").cast(pl.Datetime("ms")).dt.hour().alias("hour"))
                .with_columns(hour_radian=(2 * np.pi * h * pl.col("hour") / 24))
                .with_columns(
                    **{
                        f"hour_sin_{h}": pl.col("hour_radian").sin(),
                        f"hour_cos_{h}": pl.col("hour_radian").cos(),
                    }
                )
                .drop("hour_radian")
                .drop("hour")
            )

        return df

    def week_seasonality(self, df: pl.DataFrame) -> pl.DataFrame:
        return (
            df.with_columns(day_of_week=pl.col("timestamp").cast(pl.Datetime("ms")).dt.weekday())
            .with_columns(day_of_week_radian=2 * np.pi * pl.col("day_of_week") / 7)
            .with_columns(
                day_of_week_sin=pl.col("day_of_week_radian").sin(),
                day_of_week_cos=pl.col("day_of_week_radian").cos(),
            )
            .drop("day_of_week_radian")
            .drop("day_of_week")
        )

    def get_week_seasonality(self, df: pl.DataFrame) -> pl.DataFrame:
        return self.week_seasonality(df)

    def month_seasonality(self, df: pl.DataFrame) -> pl.DataFrame:
        return (
            df.with_columns(month=pl.col("timestamp").cast(pl.Datetime("ms")).dt.month())
            .with_columns(month_radian=2 * np.pi * pl.col("month") / 12)
            .with_columns(
                month_sin=pl.col("month_radian").sin(),
                month_cos=pl.col("month_radian").cos(),
            )
            .drop("month_radian")
            .drop("month")
        )

    def business_day_seasonality(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            is_business_day=pl.col("timestamp")
            .cast(pl.Datetime("ms"))
            .dt.weekday()
            .is_in([1, 2, 3, 4, 5])
            .cast(pl.Int8)
        )
