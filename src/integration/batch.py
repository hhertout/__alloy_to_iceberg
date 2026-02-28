from logging import Logger

import polars as pl

from configs.base import IntegrationSettings
from src.integration.catalog import CatalogClient
from utils.telemetry import get_default_attributes, get_meter

_meter = get_meter("ml_obs.integration_pipeline")

_batch_metric_size_histogram = _meter.create_histogram(
    "ml.integration_pipeline.batch_size",
    description="Number of rows in the batch",
)

_batch_metric_size_bytes_histogram = _meter.create_histogram(
    "ml.integration_pipeline.batch_size_bytes",
    description="Size of the batch in bytes",
)


class Batch:
    """A simple batch accumulator for Polars DataFrames, with a flush method to write out the batch and reset."""

    def __init__(self, logger: Logger, settings: IntegrationSettings):
        self.log = logger
        self.settings = settings
        self.data = pl.DataFrame()
        self.size_bytes: float = 0
        self.size = 0

    def add(self, df: pl.DataFrame) -> None:
        self.data = pl.concat([self.data, df], how="vertical")
        self.size += len(df)
        self.size_bytes += df.estimated_size(unit="mb")

        _batch_metric_size_histogram.record(self.size, attributes=get_default_attributes())
        _batch_metric_size_bytes_histogram.record(self.size_bytes, attributes=get_default_attributes())

    def flush(self, client: CatalogClient) -> None:
        data = self.data
        try:
            # send to storage
            self.log.info(
                "Flushing batch to storage: %d rows, %.2f MB",
                self.size,
                self.size_bytes,
            )
            client.metrics_table.append(data.to_arrow())

            # reset batch
            self.data = pl.DataFrame()
            self.size = 0
            self.size_bytes = 0

            _batch_metric_size_histogram.record(self.size, attributes=get_default_attributes())
            _batch_metric_size_bytes_histogram.record(self.size_bytes, attributes=get_default_attributes())

        except Exception as e:
            # Log the error and keep the batch for retry
            self.log.error("Failed to flush batch to storage: %s", e)
            raise e
