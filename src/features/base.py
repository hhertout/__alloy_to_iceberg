from abc import ABC, abstractmethod

import numpy as np
import polars as pl

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
        self.window_size_5m = "300000i"  # in ms, so 5min = 5*60*1000ms
        self.window_size_10m = "600000i"  # in ms, so 10min = 10*60*1000ms

        self._meter = get_meter("ml_obs.pipeline")

        self._feature_gauge = self._meter.create_gauge(
            "ml.features.number",
            description="Number of features generated after applying the feature engineering pipeline.",
        )

    @abstractmethod
    def _get_pipes(self) -> list:
        """Return the ordered list of pipe functions for this version."""
        ...

    def generate_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Applies all pipes sequentially."""
        for pipe in self._get_pipes():
            df = df.pipe(pipe)
        return df

    # -- Common features (shared across versions) --
    # Empty for now, but this is where we would add any features that are common to all versions of the pipeline.

    def get_hour_seasonality(self, df: pl.DataFrame) -> pl.DataFrame:
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

    def get_week_seasonality(self, df: pl.DataFrame) -> pl.DataFrame:
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
