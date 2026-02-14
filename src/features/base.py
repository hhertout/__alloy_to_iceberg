from abc import ABC, abstractmethod

import polars as pl

from configs.get_queries_id import get_queries_id
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
        # TODO: cast the timestamp to sin and cos to capture the cyclic nature of hours in a day
        df = df.with_columns(
            ts_sin=pl.col("timestamp").cast(pl.Int64).sin(),
            ts_cos=pl.col("timestamp").cast(pl.Int64).cos(),
        )

        return df
