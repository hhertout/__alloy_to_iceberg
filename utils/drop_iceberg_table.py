"""One-time script to drop the otlp_metrics Iceberg table so it can be recreated with the updated schema."""

from dotenv import load_dotenv
from pyiceberg.catalog import load_catalog

from configs.base import AzureSettings, load_integration_settings, load_storage_settings

load_dotenv()

integration_settings = load_integration_settings()
backend_settings = load_storage_settings()

iceberg = integration_settings.iceberg
args = {}

if isinstance(backend_settings, AzureSettings):
    args = {
        "catalog-name": iceberg.catalog_name,
        "warehouse": f"abfs://{backend_settings.container_name}@{backend_settings.account_name}.dfs.core.windows.net/warehouse",
        "adls.connection-string": backend_settings.connection_string,
    }

if iceberg.postgres is not None:
    args["catalog-type"] = "postgres"
    args["uri"] = iceberg.postgres.connection_string
    kind = "pg"
elif iceberg.polaris is not None:
    args["catalog-type"] = "rest"
    args["uri"] = iceberg.polaris.url
    args["credential"] = iceberg.polaris.token
    kind = "polaris"
else:
    raise ValueError("No catalog backend configured")

catalog = load_catalog(kind, **args)

identifier = f"{iceberg.namespace}.otlp_metrics"

try:
    catalog.drop_table(identifier)
    print(f"Table {identifier} dropped successfully.")
except Exception as e:
    print(f"Could not drop table: {e}")
