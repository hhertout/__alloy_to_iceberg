from azure.storage.blob import ContainerClient
from dotenv import load_dotenv
from pyiceberg.catalog import load_catalog

from configs.base import AzureSettings, load_integration_settings, load_storage_settings

load_dotenv()


def _warehouse_blob_prefix(warehouse_abfs_url: str) -> str:
    """Extract the blob path prefix from an abfs:// warehouse URL.

    e.g. abfs://mycontainer@myaccount.dfs.core.windows.net/lakehouse -> lakehouse/
    """
    # strip scheme and authority: abfs://<container>@<account>.dfs.core.windows.net/<path>
    path = warehouse_abfs_url.split(".dfs.core.windows.net", 1)[-1].lstrip("/")
    return path.rstrip("/") + "/"


def _load_catalog_and_settings() -> tuple:
    """Return (catalog, kind, integration_settings, backend_settings, warehouse_prefix)."""
    integration_settings = load_integration_settings()
    backend_settings = load_storage_settings()
    iceberg = integration_settings.iceberg
    args: dict[str, str | None] = {}
    warehouse_prefix = ""

    if isinstance(backend_settings, AzureSettings):
        warehouse_url = f"abfs://{backend_settings.container_name}@{backend_settings.account_name}.dfs.core.windows.net/{iceberg.warehouse_path}"
        warehouse_prefix = _warehouse_blob_prefix(warehouse_url)
        args = {
            "catalog-name": iceberg.catalog_name,
            "warehouse": warehouse_url,
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
    return catalog, integration_settings, backend_settings, warehouse_prefix


def _purge_blob_prefix(backend_settings: AzureSettings, prefix: str) -> None:
    """Delete all blobs under `prefix` in the warehouse container."""
    container_client = ContainerClient.from_connection_string(
        conn_str=backend_settings.connection_string,
        container_name=backend_settings.container_name,
    )
    blobs = list(container_client.list_blobs(name_starts_with=prefix))
    if not blobs:
        print(f"  No blobs found under {prefix}")
        return
    for blob in blobs:
        container_client.delete_blob(blob.name)
    print(f"  Deleted {len(blobs)} blob(s) under {prefix}")


def drop_iceberg_table(namespace: str, table_name: str, purge: bool = True) -> None:
    catalog, integration_settings, backend_settings, warehouse_prefix = _load_catalog_and_settings()
    identifier = f"{namespace}.{table_name}"

    try:
        catalog.drop_table(identifier)
        print(f"Table {identifier} dropped from catalog.")
    except Exception as e:
        print(f"ERROR: Could not drop table {identifier} from catalog: {e}")
        return

    if purge and isinstance(backend_settings, AzureSettings):
        prefix = f"{warehouse_prefix}{namespace}/{table_name}/"
        print(f"Purging blob data at {prefix} ...")
        _purge_blob_prefix(backend_settings, prefix)


def drop_namespace(namespace: str, purge: bool = True) -> None:
    catalog, integration_settings, backend_settings, warehouse_prefix = _load_catalog_and_settings()

    try:
        catalog.drop_namespace(namespace)
        print(f"Namespace {namespace} dropped from catalog.")
    except Exception as e:
        print(f"ERROR: Could not drop namespace {namespace} from catalog: {e}")
        return

    if purge and isinstance(backend_settings, AzureSettings):
        prefix = f"{warehouse_prefix}{namespace}/"
        print(f"Purging blob data at {prefix} ...")
        _purge_blob_prefix(backend_settings, prefix)
