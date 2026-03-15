from enum import Enum

from pyiceberg.catalog import Catalog
from pyiceberg.table import Table

from src.integration.migrations.migrator import MetricsMigration
from src.integration.schema.log import LOG_PARTITION_SPEC, LOG_SCHEMA
from src.integration.schema.metric import METRIC_PARTITION_SPEC, METRIC_SCHEMA


class TableKind(Enum):
    METRIC = "metric"
    LOG = "log"


class TableManager:
    def create_tables(self, catalog: Catalog, namespace: str) -> None:
        self.__create_table(catalog, namespace, TableKind.METRIC)
        self.__create_table(catalog, namespace, TableKind.LOG)

    def __create_table(self, catalog: Catalog, namespace: str, kind: TableKind) -> None:
        table_name = f"otlp_{kind.value}"
        identifier = f"{namespace}.{table_name}"
        properties = {"write.parquet.compression-codec": "zstd"}

        try:
            if kind == TableKind.METRIC:
                self.metrics_table = catalog.create_table(
                    identifier,
                    schema=METRIC_SCHEMA,
                    partition_spec=METRIC_PARTITION_SPEC,
                    properties=properties,
                )
            elif kind == TableKind.LOG:
                self.log_table = catalog.create_table(
                    identifier,
                    schema=LOG_SCHEMA,
                    partition_spec=LOG_PARTITION_SPEC,
                    properties=properties,
                )
        except Exception as e:
            if "already exists" not in str(e):
                raise e
            if kind == TableKind.METRIC:
                self.metrics_table = catalog.load_table(identifier)
                self.__execute_migration(self.metrics_table)
            elif kind == TableKind.LOG:
                self.log_table = catalog.load_table(identifier)
                self.__execute_migration(self.log_table)

    def __execute_migration(self, table: Table) -> None:
        MetricsMigration(table).migrate()
