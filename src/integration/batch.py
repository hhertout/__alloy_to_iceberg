from logging import Logger
from typing import Literal

import polars as pl

from configs.base import IntegrationSettings
from src.integration.catalog import CatalogClient
from utils.telemetry import get_default_attributes, get_meter

_meter = get_meter("ml_obs.integration_pipeline")

_batch_metric_size_histogram = _meter.create_histogram(
    "ml.integration_pipeline.batch_size",
    description="Number of rows accumulated in the current batch",
)

_batch_metric_rows_counter = _meter.create_counter(
    "ml.integration_pipeline.batch_rows",
    description="Total number of rows added to the batch",
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
        self._metric_frames: list[pl.DataFrame] = []
        self._log_frames: list[pl.DataFrame] = []
        self.size_bytes: float = 0
        self.size = 0

    def add(self, df: pl.DataFrame, kind: Literal["metric", "log"]) -> None:
        self.log.debug(f"Adding {len(df)} rows to batch (kind={kind})")
        if kind == "metric":
            self._metric_frames.append(df)
        elif kind == "log":
            self._log_frames.append(df)
        else:
            raise ValueError(f"Unknown batch kind: {kind}")

        self.size += len(df)
        self.size_bytes += df.estimated_size(unit="mb")

        _batch_metric_size_histogram.record(
            self.size, attributes={**get_default_attributes(), "batch": kind}
        )
        _batch_metric_rows_counter.add(
            len(df), attributes={**get_default_attributes(), "batch": kind}
        )
        _batch_metric_size_bytes_histogram.record(
            self.size_bytes, attributes={**get_default_attributes(), "batch": kind}
        )

    def flush(self, client: CatalogClient) -> None:
        metric_data = (
            pl.concat(self._metric_frames, how="vertical")
            if self._metric_frames
            else pl.DataFrame()
        )
        log_data = (
            pl.concat(self._log_frames, how="vertical") if self._log_frames else pl.DataFrame()
        )

        metric_rows = len(metric_data)
        log_rows = len(log_data)
        metric_bytes = metric_data.estimated_size(unit="mb") if metric_rows else 0
        log_bytes = log_data.estimated_size(unit="mb") if log_rows else 0

        try:
            self.log.info(
                "Flushing batch to storage: %d rows (metrics=%d, logs=%d), %.2f MB",
                self.size,
                metric_rows,
                log_rows,
                self.size_bytes,
            )

            # flush metrics
            if not metric_data.is_empty():
                client.table_manager.metrics_table.append(metric_data.to_arrow())
                _batch_metric_size_histogram.record(
                    metric_rows, attributes={**get_default_attributes(), "batch": "metric"}
                )
                _batch_metric_size_bytes_histogram.record(
                    metric_bytes, attributes={**get_default_attributes(), "batch": "metric"}
                )

            # flush logs
            if not log_data.is_empty():
                client.table_manager.log_table.append(log_data.to_arrow())
                _batch_metric_size_histogram.record(
                    log_rows, attributes={**get_default_attributes(), "batch": "log"}
                )
                _batch_metric_size_bytes_histogram.record(
                    log_bytes, attributes={**get_default_attributes(), "batch": "log"}
                )

            # reset both lists only after both flushes succeed
            self._metric_frames = []
            self._log_frames = []
            self.size = 0
            self.size_bytes = 0

        except Exception as e:
            self.log.error("Failed to flush batch to storage: %s", e)
            raise e
