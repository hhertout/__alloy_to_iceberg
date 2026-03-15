---
title: "ADR-006: Multi-cloud storage backend (ADLS and S3)"
status: accepted
date: 2026-03-15
---

# ADR-006: Multi-cloud storage backend (ADLS and S3)

## Context

The Iceberg tables need a durable object store for data files and metadata. The project must support deploying to different cloud environments depending on the organization:

- **Azure Blob Storage (ADLS Gen2):** Primary target for production workloads.
- **Amazon S3 (or S3-compatible):** Used in development with MinIO and as an alternative production backend.

The storage backend must be configurable without code changes, and the same Iceberg catalog code must work against both storage systems.

## Alternatives considered

### Azure Blob Storage only

Lock to ADLS as the sole backend.

- **Pros:** Simpler configuration. One set of credentials.
- **Cons:** Prevents local development without Azure access. Can't deploy to AWS environments. Locks out MinIO for integration testing.

### S3 only (with MinIO for Azure-like environments)

Use S3 API everywhere, including S3-compatible gateways for Azure.

- **Pros:** Single API surface. MinIO provides a local S3 endpoint.
- **Cons:** Azure native tooling (AzCopy, ADLS firewall rules, managed identities) becomes unavailable. S3 gateways in front of Azure add latency and operational complexity.

### Abstract storage interface

Build a custom abstraction layer that hides the storage backend behind a unified API.

- **Pros:** Clean separation of concerns.
- **Cons:** Over-engineering. PyIceberg and `fsspec` already abstract storage access through `adlfs` (Azure) and `s3fs` (S3). Adding another layer duplicates existing functionality.

## Decision

Support both **Azure Blob Storage (ADLS)** and **Amazon S3** as storage backends, configured via the `storage_kind` setting (`adls` or `s3`).

## Implementation

The `CatalogClient` in `src/integration/catalog.py` builds warehouse URLs and filesystem credentials based on `storage_kind`:

- **ADLS:** Warehouse path is `abfss://<CONTAINER>@<ACCOUNT>.dfs.core.windows.net/`. Properties include `adlfs.account-name` and `adlfs.sas-token` or `adlfs.account-key`.
- **S3:** Warehouse path is `s3://<BUCKET>/`. Properties include `s3.endpoint`, `s3.access-key-id`, and `s3.secret-access-key`.

PyIceberg resolves the correct `fsspec` filesystem implementation automatically based on the URI scheme (`abfss://` or `s3://`).

The `docker-compose.yml` includes a MinIO service for local S3-compatible development, pre-configured with a `warehouse` bucket.

## Rationale

- **Cloud flexibility:** Different teams and environments use different clouds. Supporting both ADLS and S3 prevents vendor lock-in at the storage layer.
- **Local development:** MinIO provides a lightweight S3-compatible endpoint that runs in Docker. Developers can test the full pipeline locally without cloud credentials.
- **Leverage existing abstractions:** PyIceberg uses Apache Arrow's filesystem layer (`fsspec`), which already supports `adlfs` and `s3fs`. The project only needs to pass the correct configuration properties — no custom I/O code.
- **Configuration-driven:** Switching between backends requires changing `storage_kind`, container/bucket name, and credentials in the config. No code changes needed.

## Consequences

- Two sets of credentials and configuration paths must be maintained. Environment-specific configs (for example, `.env.azure`, `.env.s3`) should be documented.
- Storage-specific features (ADLS hierarchical namespace, S3 lifecycle policies) must be configured outside the application. The project doesn't manage storage-level settings.
- Integration tests should cover both backends to catch storage-specific edge cases (`adlfs` and `s3fs` have different error handling and retry behaviors).
- The `push_to_blob.py` legacy script uses `src/client/azure.py` and `src/client/s3.py` for direct blob operations outside the Iceberg layer. These clients are independent of the catalog's storage abstraction.

## Related

- [ADR-001: Iceberg as lakehouse format](./ADR-001-iceberg-lakehouse-format.md)
- [ADR-005: Partitioning strategy](./ADR-005-partitioning-strategy.md)
