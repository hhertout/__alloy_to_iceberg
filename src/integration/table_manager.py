from src.integration.catalog import CatalogClient
from src.integration.migrations.migrator import MetricsMigration
from src.integration.schema.metric import METRIC_SCHEMA
from src.integration.schema.log import LOG_SCHEMA
from pyiceberg.table import Table
from enum import Enum

class TableKind(Enum):
    METRIC = "metric"
    LOG = "log"

class TableManager:
    def create_tables(self, client: CatalogClient, namespace: str) -> None:
        self.__create_table(client, namespace, TableKind.METRIC)
        self.__create_table(client, namespace, TableKind.LOG)

    def __create_table(self, client: CatalogClient, namespace: str, kind: TableKind) -> None:
        table_name = f"otlp_{kind.value}"
        identifier = f"{namespace}.{table_name}"
        properties = {"write.parquet.compression-codec": "zstd"}

        try:
            if kind == TableKind.METRIC:
                self.metrics_table = client.create_table(
                    identifier, schema=METRIC_SCHEMA, properties=properties
                )
            elif kind == TableKind.LOG:
                self.log_table = client.create_table(
                    identifier, schema=LOG_SCHEMA, properties=properties
                )
        except Exception as e:
            if "already exists" not in str(e):
                raise e
            if kind == TableKind.METRIC:
                self.metrics_table = client.load_table(identifier)
                self.__execute_migration(self.metrics_table)
            elif kind == TableKind.LOG:
                self.log_table = client.load_table(identifier)
                self.__execute_migration(self.log_table)

    def __execute_migration(self, table: Table) -> None:
        MetricsMigration(table).migrate()