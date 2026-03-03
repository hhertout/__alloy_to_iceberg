# CLI

This document describes the `scripts/cli.py` command-line interface for managing the Iceberg catalog.

Before you begin, ensure you have the following:

- Dependencies installed (`uv sync --dev`)
- A `.env` file or environment variables configured for your storage and catalog backend (refer to the [Environment variables](#environment-variables) section)

## Overview

The CLI lets you manage catalog objects (namespaces and tables) directly from the terminal. It targets the Iceberg catalog defined in `configs/config.yaml` and, by default, also purges the associated blob data from Azure Blob Storage when dropping an object.

It supports two modes:

- **Interactive mode** — prompts you step by step when run without arguments.
- **Non-interactive mode** — accepts arguments directly, suitable for scripting.

## Usage

```sh
uv run python scripts/cli.py <command> <target> [options]
```

### Interactive mode

Run without arguments to get a guided prompt:

```sh
uv run python scripts/cli.py
```

The output will resemble the following:

```text
Iceberg Catalog Management:
Please select the action you want to perform:
1. Delete Namespace
2. Drop Tables
Action to perform (1 or 2):
```

## Commands

### `delete namespace`

Drops a namespace from the Iceberg catalog and purges all associated blobs from Azure Blob Storage.

```sh
uv run python scripts/cli.py delete namespace -n <NAMESPACE>
```

To keep the blob data and only remove the catalog entry:

```sh
uv run python scripts/cli.py delete namespace -n <NAMESPACE> --no-purge
```

### `delete table`

Drops a table from the Iceberg catalog and purges all associated blobs from Azure Blob Storage.

```sh
uv run python scripts/cli.py delete table -n <NAMESPACE> -t <TABLE>
```

To keep the blob data and only remove the catalog entry:

```sh
uv run python scripts/cli.py delete table -n <NAMESPACE> -t <TABLE> --no-purge
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--namespace` | `-n` | Namespace to target |
| `--table` | `-t` | Table to target |
| `--no-purge` | — | Skips deletion of blob storage data; only removes the catalog entry |

## Purge behavior

By default, dropping a namespace or table also **deletes all blobs** under the corresponding path in Azure Blob Storage:

| Operation | Blob prefix deleted |
|-----------|---------------------|
| `delete namespace` | `<warehouse>/<namespace>/` |
| `delete table` | `<warehouse>/<namespace>/<table>/` |

This is a destructive and irreversible operation. Use `--no-purge` if you only want to remove the catalog entry while preserving the raw data.

## Environment variables

The CLI reads its configuration from `configs/config.yaml` and resolves `$VAR` references from environment variables. Create a `.env` file at the project root:

```sh
# Iceberg catalog backend (PostgreSQL)
POSTGRESQL_CONNECTION_STRING=postgresql://user:password@host:5432/db

# Azure Blob Storage
AZURE_STORAGE_ACCOUNT_NAME=<ACCOUNT_NAME>
AZURE_STORAGE_CONTAINER_NAME=<CONTAINER_NAME>
AZURE_STORAGE_CONNECTION_STRING=<CONNECTION_STRING>
```

## Examples

Drop the `obs` namespace and all its data:

```sh
uv run python scripts/cli.py delete namespace -n obs
```

Drop the `metrics` table from the `obs` namespace without touching blob storage:

```sh
uv run python scripts/cli.py delete table -n obs -t metrics --no-purge
```

## Related documentation

- [Architecture](./architecture.md) — Iceberg data lake architecture
- [Local stack](./local-stack.md) — local Polaris and PostgreSQL catalog setup
- [Runbook](./runbook.md) — operational procedures
