from pyiceberg.catalog import load_catalog

from configs.base import AzureSettings, IntegrationSettings, load_storage_settings
from src.integration.table_manager import TableManager


class CatalogClient:
    def __init__(self, settings: IntegrationSettings):
        self._settings = settings
        self._backend_settings = load_storage_settings()
        self.table_manager = TableManager()

        if settings.iceberg.postgres is not None:
            self.kind = "pg"
        elif settings.iceberg.polaris is not None:
            self.kind = "polaris"
        elif settings.iceberg.unity is not None:
            self.kind = "unity"
        else:
            raise ValueError("Unsupported catalog backend in settings")

        if isinstance(self._backend_settings, AzureSettings):
            self.storage_kind = "azure"
        else:
            self.storage_kind = "s3"

    def load_catalog(self) -> None:
        args: dict[str, str | None] = {}

        if isinstance(self._backend_settings, AzureSettings):
            args = {
                "catalog-name": self._settings.iceberg.catalog_name,
                "warehouse": f"abfs://{self._backend_settings.container_name}@{self._backend_settings.account_name}.dfs.core.windows.net/{self._settings.iceberg.warehouse_path}",
                "adls.connection-string": self._backend_settings.connection_string,
            }
        else:
            args = {
                "warehouse": f"s3://{self._backend_settings.bucket_name}/{self._settings.iceberg.warehouse_path}",
                "s3.endpoint": self._backend_settings.endpoint_url,
                "s3.access-key-id": self._backend_settings.aws_access_key_id,
                "s3.secret-access-key": self._backend_settings.aws_secret_access_key,
                "s3.region": self._backend_settings.region_name,
            }

        if self._settings.iceberg.postgres is not None:
            postgres = self._settings.iceberg.postgres
            args["catalog-type"] = "postgres"
            args["uri"] = postgres.connection_string
        elif self._settings.iceberg.polaris is not None:
            polaris = self._settings.iceberg.polaris
            args["catalog-type"] = "rest"
            args["uri"] = polaris.url
            args["credential"] = polaris.token
        elif self._settings.iceberg.unity is not None:
            unity = self._settings.iceberg.unity
            args["catalog-type"] = "rest"
            args["uri"] = f"{unity.workspace_url}/api/2.1/unity-catalog/iceberg"
            args["token"] = unity.token
            # Unity Catalog manages storage locations internally
            args.pop("warehouse", None)

        self.catalog = load_catalog(self.kind, **args)

    def create_namespace(self) -> None:
        if self._settings.iceberg.namespace is not None:
            try:
                self.catalog.create_namespace(self._settings.iceberg.namespace)
            except Exception as e:
                if "already exists" in str(e):
                    pass
                else:
                    raise e

    def create_tables(self) -> None:
        namespace = self._settings.iceberg.namespace
        if namespace is None:
            raise ValueError("Cannot create tables: iceberg.namespace is not configured")
        self.table_manager.create_tables(self.catalog, namespace)
