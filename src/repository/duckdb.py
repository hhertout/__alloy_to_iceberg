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
        self.metrics_table = self.catalog_client.table_manager.metrics_table.location()
        self.conn = self.catalog_client.table_manager.metrics_table.scan().to_duckdb(
            table_name="otlp_metrics"
        )

    def get_data_for_training(self) -> pl.DataFrame:
        """
        Complete method to interface with blob storage, retrieve data, and prepare it for training.
        This is an abstraction to avoid unnecessary dependencies in the training script and to encapsulate all blob storage interactions in one place.
        """
        df = cast(
            pl.DataFrame,
            self.conn.execute("""
            WITH
            -- Process attr and resource_attr
            metric_table AS (
                SELECT
                    timestamp,
                    __name__,
                    value,
                    service_name,
                    service_namespace,
                    k8s_namespace_name,
                    cluster_name,
                    env,
                    MAP(
                        LIST_TRANSFORM(attributes, x -> x.key),
                        LIST_TRANSFORM(attributes, x -> x.value)
                    ) as attributes,
                    MAP(
                        LIST_TRANSFORM(resource_attributes, x -> x.key),
                        LIST_TRANSFORM(resource_attributes, x -> x.value)
                    ) as resource_attributes
                FROM otlp_metrics
            )
            SELECT
                (INTERVAL '5 minutes', timestamp) AS bucket,
                __name__,
                AVG(value) AS value,
                attributes,
                resource_attributes
            FROM metric_table
            WHERE timestamp > now() - INTERVAL '7 days'
            GROUP BY ALL
        """).pl(),
        )

        return df
