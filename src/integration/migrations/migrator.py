from pyiceberg.table import Table


class MetricsMigration:
    """
    Class to handle migrations for the metrics table.
    Each migration should be implemented as a separate method, and the migrate() method should call them in the correct order.
    Please name the migration methods with a version number (e.g., __v01, __v02) to keep track of the migration history and ensure they are executed in the correct order.
    For each migration, place it in the migrate() method in the correct order, and implement the migration logic in the corresponding __vXX method.
    The migration methods should use the update_schema() context manager to perform schema updates, and should not commit any changes outside of this context manager to ensure atomicity of the migration.
    """

    def __init__(self, table_ref: Table) -> None:
        self.table = table_ref

    def migrate(self) -> None:
        self.__v01()

    def __v01(self) -> None:
        with self.table.update_schema() as _update:
            # TODO: place your migration code here, for example:
            # _update.add_column("service_namespace", StringType(), required=False)
            pass
