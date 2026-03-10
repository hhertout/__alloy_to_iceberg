# Kubernetes deployment

This document describes how to deploy bumblebib on Kubernetes using the Helm chart located in `.k8s/bumblebib/`.

Before you begin, ensure you have the following:

- [Helm](https://helm.sh/docs/intro/install/) v3+
- A running Kubernetes cluster with `kubectl` configured
- The bumblebib Docker image built and pushed to a registry accessible by your cluster
- A Kubernetes Secret containing the required credentials (refer to the [Secrets](#secrets) section)

## Architecture

The chart deploys two workloads from the same image.

```
Grafana
┌─────────────────────────┐
│  Prometheus datasource  │──▶┐
│  Loki datasource        │──▶┤  ┌──────────────────────┐       ┌──────────────────┐
└─────────────────────────┘   └─▶│ producer             │──────▶│ Kafka            │
                                 │ metrics_producer.py  │──────▶│  topic: metrics  │──▶┐
                                 └──────────────────────┘       │  topic: logs     │──▶┤
                                                                └──────────────────┘   │
                                ┌──────────────────────┐                               │
                                │ consumer             │◀──────────────────────────────┘
                                │ integration_         │
                                │ pipeline.py          │
                                └──────────┬───────────┘
                                           │
                                           ▼
                                 ┌─────────────────────┐
                                 │ Iceberg             │
                                 │ (PostgreSQL catalog)│
                                 └─────────────────────┘
```

## Chart structure

```
.k8s/bumblebib/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── _helpers.tpl
    ├── serviceaccount.yaml
    ├── producer.yaml
    ├── producer-hpa.yaml
    ├── consumer.yaml
    └── consumer-hpa.yaml
```

## Secrets

The application reads credentials from environment variables. Create a Kubernetes Secret before deploying:

```sh
kubectl create secret generic bumblebib-secrets \
  --from-literal=grafana-sa-token=<GRAFANA_SA_TOKEN> \
  --from-literal=kafka-broker=<KAFKA_BROKER> \
  --from-literal=postgresql-connection-string=<POSTGRESQL_CONNECTION_STRING> \
  --from-literal=azure-storage-connection-string=<AZURE_STORAGE_CONNECTION_STRING>
```

Reference the Secret in your `values.yaml` via `extraEnv`:

```yaml
consumer:
  extraEnv:
    - name: KAFKA_BROKER
      valueFrom:
        secretKeyRef:
          name: bumblebib-secrets
          key: kafka-broker
    - name: POSTGRESQL_CONNECTION_STRING
      valueFrom:
        secretKeyRef:
          name: bumblebib-secrets
          key: postgresql-connection-string
    - name: AZURE_STORAGE_CONNECTION_STRING
      valueFrom:
        secretKeyRef:
          name: bumblebib-secrets
          key: azure-storage-connection-string

producer:
  extraEnv:
    - name: GRAFANA_SA_TOKEN
      valueFrom:
        secretKeyRef:
          name: bumblebib-secrets
          key: grafana-sa-token
    - name: KAFKA_BROKER
      valueFrom:
        secretKeyRef:
          name: bumblebib-secrets
          key: kafka-broker
```

## Configuration

The following table describes the main `values.yaml` options.

### Image

| Key | Default | Description |
|-----|---------|-------------|
| `image.repository` | `bumblebib` | Docker image repository |
| `image.tag` | `latest` | Image tag |
| `image.pullPolicy` | `IfNotPresent` | Pull policy |
| `imagePullSecrets` | `[]` | Secrets for private registries |

### Service account

| Key | Default | Description |
|-----|---------|-------------|
| `serviceAccount.create` | `false` | Creates a dedicated ServiceAccount when `true` |
| `serviceAccount.name` | `""` | Name override (uses generated name if empty) |

### Producer

| Key | Default | Description |
|-----|---------|-------------|
| `producer.enabled` | `true` | Deploys the producer when `true` |
| `producer.replicas` | `1` | Number of replicas (ignored when HPA is enabled) |
| `producer.extraEnv` | `[]` | Environment variables injected into the container |
| `producer.resources` | see below | CPU and memory requests/limits |
| `producer.scaling.enabled` | `false` | Enables HPA |
| `producer.scaling.minReplicas` | `1` | HPA minimum replicas |
| `producer.scaling.maxReplicas` | `5` | HPA maximum replicas |
| `producer.scaling.targetCPUUtilizationPercentage` | `80` | HPA CPU target |
| `producer.scaling.targetMemoryUtilizationPercentage` | `80` | HPA memory target |

### Consumer

| Key | Default | Description |
|-----|---------|-------------|
| `consumer.enabled` | `true` | Deploys the consumer when `true` |
| `consumer.replicas` | `2` | Number of replicas (ignored when HPA is enabled) |
| `consumer.terminationGracePeriodSeconds` | `60` | Grace period for in-flight batch processing on shutdown |
| `consumer.extraEnv` | `[]` | Environment variables injected into the container |
| `consumer.resources` | see below | CPU and memory requests/limits |
| `consumer.scaling.enabled` | `true` | Enables HPA |
| `consumer.scaling.minReplicas` | `1` | HPA minimum replicas |
| `consumer.scaling.maxReplicas` | `5` | HPA maximum replicas |
| `consumer.scaling.targetCPUUtilizationPercentage` | `80` | HPA CPU target |
| `consumer.scaling.targetMemoryUtilizationPercentage` | `80` | HPA memory target |

### Default resources

```yaml
# Producer — light workload (periodic scrape)
resources:
  requests:
    cpu: "50m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"

# Consumer — heavier workload (Kafka + Iceberg writes)
resources:
  requests:
    cpu: "250m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
```

## Deploy

### Install

To install the chart into the `bumblebib` namespace:

```sh
helm install bumblebib .k8s/bumblebib \
  --namespace bumblebib \
  --create-namespace \
  --values .k8s/bumblebib/values.yaml \
  --values path/to/values-prod.yaml
```

### Upgrade

To upgrade a running release:

```sh
helm upgrade bumblebib .k8s/bumblebib \
  --namespace bumblebib \
  --values .k8s/bumblebib/values.yaml \
  --values path/to/values-prod.yaml
```

### Uninstall

To remove the release:

```sh
helm uninstall bumblebib --namespace bumblebib
```

## Verify

To verify the deployment after installing:

```sh
# Check pod status
kubectl get pods -n bumblebib

# Check logs for a specific workload
kubectl logs -n bumblebib -l app.kubernetes.io/component=producer --tail=50
kubectl logs -n bumblebib -l app.kubernetes.io/component=consumer --tail=50

# Inspect a rendered release
helm show chart .k8s/bumblebib
helm get manifest bumblebib -n bumblebib
```

## Scaling

The consumer HPA is enabled by default and scales on CPU and memory utilization. The producer is a single-replica scraper and doesn't benefit from horizontal scaling — its HPA is disabled by default.

When HPA is enabled for a workload, the `replicas` field is omitted from the Deployment spec so that Helm upgrades don't override the replica count managed by the HPA.

## Related documentation

- [Architecture](./architecture.md) — pipeline architecture and data flow
- [Runbook](./runbook.md) — operational procedures
- [Helm documentation](https://helm.sh/docs/)
