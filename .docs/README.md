# Internal documentation

## Index

| Document | Description |
|----------|-------------|
| [dev-practices.md](./dev-practices.md) | Developer guide & best practices |
| [local-stack.md](./local-stack.md) | Local Docker Compose stack (Grafana, Alloy, Prometheus, Loki) |
| [architecture.md](./architecture.md) | Project architecture |
| [runbook.md](./runbook.md) | Operational procedures |
| [qa.md](./qa.md) | Quality assurance |
| [real-time-prediction.md](./real-time-prediction.md) | Real-time streaming prediction architecture |
| [polaris.md](./polaris.md) | Apache Polaris user manual (Iceberg catalog) |
| [kubernetes.md](./kubernetes.md) | Kubernetes deployment with Helm |
| [cli.md](./cli.md) | Iceberg catalog management CLI |
| [configuration.md](./configuration.md) | Full configuration parameter reference |

## Quick start

```sh
# Full setup (deps + pre-commit)
make setup

# Start local stack
docker compose up -d

# Validate code before pushing
make fix
make validate
```

## Local links

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | - |
| Alloy | http://localhost:12345 | - |
| Loki | http://localhost:3100 | - |
| Polaris API | http://localhost:8181 | root / s3cr3t |
| Polaris management | http://localhost:8182 | - |
