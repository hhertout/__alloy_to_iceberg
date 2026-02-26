# Apache Polaris — user manual

Apache Polaris is an open-source catalog for Apache Iceberg. It exposes a REST API that clients (PyIceberg, Spark, Trino, etc.) use to discover and manage tables. In this stack, Polaris runs locally via Docker Compose and uses an in-memory store.

Before you begin, ensure you have the following:

- Docker Compose stack running (`docker compose up -d`)
- `curl` available in your terminal
- (optional) PyIceberg installed (`uv add pyiceberg`)

## Architecture

```
┌─────────────────────────────────────────────┐
│                Apache Polaris               │
│                                             │
│   :8181  Catalog REST API  (Iceberg)        │
│   :8182  Management API   (health/metrics)  │
└─────────────────────────────────────────────┘
```

Polaris models a three-level hierarchy:

```
Catalog
 └── Namespace  (can be nested: ns1.ns2)
      └── Table  (Apache Iceberg table)
```

## Authentication

Polaris uses OAuth 2.0 client credentials. Every API call requires a bearer token obtained from the token endpoint.

The local stack is bootstrapped with the following credentials:

| Field | Value |
|-------|-------|
| `client_id` | `root` |
| `client_secret` | `s3cr3t` |
| `realm` | `POLARIS` |

### Get a token

Send a `POST` request to the OAuth token endpoint:

```sh
curl -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL'
```

The response contains an `access_token` field:

```json
{
  "access_token": "<TOKEN>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Export the token for reuse

Export the token as a shell variable to reuse it across commands:

```sh
export POLARIS_TOKEN=$(curl -sf \
  -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
```

All subsequent commands use `-H "Authorization: Bearer $POLARIS_TOKEN"`.

## Catalog management

A catalog is the top-level container. It defines the storage backend (local filesystem, S3, Azure, etc.) and the default base location for table data.

### List catalogs

```sh
curl -sf \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  http://localhost:8181/api/management/v1/catalogs
```

### Create a catalog

The example below creates an `INTERNAL` catalog backed by the local filesystem:

```sh
curl -sf -X POST \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:8181/api/management/v1/catalogs \
  -d '{
    "name": "my_catalog",
    "type": "INTERNAL",
    "properties": {
      "default-base-location": "file:///tmp/polaris/my_catalog"
    }
  }'
```

Replace `file:///tmp/polaris/my_catalog` with an S3 or Azure URL for cloud storage.

### Delete a catalog

```sh
curl -sf -X DELETE \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  http://localhost:8181/api/management/v1/catalogs/my_catalog
```

## Namespace management

Namespaces organise tables within a catalog. They can be nested with a `.` separator (for example `data.raw`).

The namespace endpoints use the Iceberg REST catalog path: `/api/catalog/v1/<catalog>/namespaces`.

### List namespaces

```sh
curl -sf \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  http://localhost:8181/api/catalog/v1/my_catalog/namespaces
```

### Create a namespace

```sh
curl -sf -X POST \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:8181/api/catalog/v1/my_catalog/namespaces \
  -d '{"namespace": ["data"]}'
```

For a nested namespace (for example `data.raw`):

```sh
curl -sf -X POST \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:8181/api/catalog/v1/my_catalog/namespaces \
  -d '{"namespace": ["data", "raw"]}'
```

### Delete a namespace

```sh
curl -sf -X DELETE \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  http://localhost:8181/api/catalog/v1/my_catalog/namespaces/data
```

## Table management

Tables represent Apache Iceberg tables. Each table belongs to a namespace.

### List tables

```sh
curl -sf \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  http://localhost:8181/api/catalog/v1/my_catalog/namespaces/data/tables
```

### Create a table

The request body follows the Iceberg REST spec. The example below creates a table with a simple schema:

```sh
curl -sf -X POST \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:8181/api/catalog/v1/my_catalog/namespaces/data/tables \
  -d '{
    "name": "metrics",
    "schema": {
      "type": "struct",
      "schema-id": 0,
      "fields": [
        {"id": 1, "name": "timestamp", "required": true,  "type": "timestamptz"},
        {"id": 2, "name": "name",      "required": true,  "type": "string"},
        {"id": 3, "name": "value",     "required": false, "type": "double"}
      ]
    }
  }'
```

### Load table metadata

```sh
curl -sf \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  http://localhost:8181/api/catalog/v1/my_catalog/namespaces/data/tables/metrics
```

### Delete a table

```sh
curl -sf -X DELETE \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  http://localhost:8181/api/catalog/v1/my_catalog/namespaces/data/tables/metrics
```

## Python integration (PyIceberg)

PyIceberg can use Polaris as its REST catalog. Install the package first:

```sh
uv add "pyiceberg[pyarrow]"
```

### Connect to the catalog

```python
from pyiceberg.catalog import load_catalog

catalog = load_catalog(
    "polaris",
    **{
        "type": "rest",
        "uri": "http://localhost:8181/api/catalog/v1",
        "credential": "root:s3cr3t",
        "warehouse": "my_catalog",
        "scope": "PRINCIPAL_ROLE:ALL",
    },
)
```

The `credential` field has the format `<client_id>:<client_secret>`. PyIceberg handles token refresh automatically.

### Common operations

List all namespaces:

```python
catalog.list_namespaces()
```

Create a namespace:

```python
catalog.create_namespace("data")
```

Create a table from a PyArrow schema:

```python
import pyarrow as pa
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, TimestamptzType, StringType, DoubleType

schema = Schema(
    NestedField(1, "timestamp", TimestamptzType(), required=True),
    NestedField(2, "name",      StringType(),      required=True),
    NestedField(3, "value",     DoubleType(),      required=False),
)

table = catalog.create_table("data.metrics", schema=schema)
```

Load an existing table and append data:

```python
import pyarrow as pa

table = catalog.load_table("data.metrics")
df = pa.table({
    "timestamp": pa.array(["2026-02-25T00:00:00Z"], type=pa.timestamp("us", tz="UTC")),
    "name":      pa.array(["cpu_usage"]),
    "value":     pa.array([42.5]),
})
table.append(df)
```

## Management endpoints

The management port `8182` exposes Quarkus health and metrics endpoints.

### Health check

```sh
curl http://localhost:8182/q/health
```

The response indicates whether the service and its dependencies (database connection) are healthy:

```json
{
  "status": "UP",
  "checks": [
    {"name": "Database connections health check", "status": "UP"}
  ]
}
```

### Prometheus metrics

```sh
curl http://localhost:8182/q/metrics
```

### Readiness and liveness probes

```sh
# Readiness
curl http://localhost:8182/q/health/ready

# Liveness
curl http://localhost:8182/q/health/live
```

## Next steps

- [Apache Polaris documentation](https://polaris.apache.org)
- [Iceberg REST catalog spec](https://iceberg.apache.org/concepts/catalog/)
- [PyIceberg documentation](https://py.iceberg.apache.org)
- [Local development stack](./local-stack.md)
