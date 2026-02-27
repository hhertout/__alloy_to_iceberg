from pyiceberg.catalog import load_catalog

from configs.base import AzureSettings, IntegrationSettings, load_storage_settings
from src.integration.schema.metric import METRICS_SCHEMA


class CatalogClient:
    def __init__(self, settings: IntegrationSettings):
        self._settings = settings
        self._backend_settings = load_storage_settings()

        if settings.iceberg.postgres is not None:
            self.kind = "pg"
        elif settings.iceberg.polaris is not None:
            self.kind = "polaris"
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
                "warehouse": f"abfs://{self._backend_settings.container_name}@{self._backend_settings.account_name}.dfs.core.windows.net/warehouse",
                "adls.connection-string": self._backend_settings.connection_string,
            }
        else:
            args = {
                "warehouse": f"s3://{self._backend_settings.bucket_name}/warehouse",
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
        identifier = f"{self._settings.iceberg.namespace}.otlp_metrics"
        try:
            self.metrics_table = self.catalog.create_table(identifier, schema=METRICS_SCHEMA)
        except Exception as e:
            if "already exists" in str(e):
                self.metrics_table = self.catalog.load_table(identifier)
            else:
                raise e
