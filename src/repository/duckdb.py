from typing import cast

import duckdb
import polars as pl

from configs.base import load_integration_settings
from src.integration.catalog import CatalogClient


class BlobRepository:
    """
    Repository class to interface with blob storage and retrieve data for training.
    This class is dedicated to data retrieval via DuckDB.

    Do not use it for any other purpose to avoid unnecessary dependencies in the training script and to encapsulate all blob storage interactions in one place.
    """

    def __init__(self) -> None:
        self.__integration_settings = load_integration_settings()
        self.catalog_client = CatalogClient(self.__integration_settings)
        self.catalog_client.load_catalog()

        self.conn = duckdb.connect()
        self.__prepare()

    def __prepare(self) -> None:
        """
        Load the metrics table from the catalog and prepare the DuckDB connection for querying.
        ATM, only the table metrics are loaded, but this can be extended in the future if needed.
        """
        self.catalog_client.create_tables()
        self.metrics_table = self.catalog_client.metrics_table.location()
        self.conn = self.catalog_client.metrics_table.scan().to_duckdb(table_name="otlp_metrics")

    def get_data_for_training(self) -> pl.DataFrame:
        """
        Complete method to interface with blob storage, retrieve data, and prepare it for training.
        This is an abstraction to avoid unnecessary dependencies in the training script and to encapsulate all blob storage interactions in one place.
        """
        df = cast(
            pl.DataFrame,
            self.conn.execute("""
            SELECT *
            FROM otlp_metrics
            WHERE timestamp > now() - INTERVAL '7 days'
        """).pl(),
        )

        df.write_parquet("output/training_data.parquet")

        return df
