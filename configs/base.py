import os
from functools import lru_cache
from typing import Any

import yaml
from pydantic import BaseModel

from configs.constants import (
    DEFAULT_AZ_FILE_EXTENSION,
    DEFAULT_AZ_FILE_IDENTIFIER,
    DEFAULT_AZ_FILE_PREFIX,
    DEFAULT_LIMITS_TARGET_COL_NAME,
    DEFAULT_S3_FILE_EXTENSION,
    DEFAULT_S3_FILE_IDENTIFIER,
    DEFAULT_S3_FILE_PREFIX,
    DEFAULTS_LIMITS_DF_SPLIT_SIZE,
    DEFAULTS_LIMITS_OFFSET_DAYS,
    DEFAULTS_LIMITS_TRAINING_WINDOW_DAYS,
)

_DEFAULT_OTLP_ENDPOINT = "http://localhost:4317"
_DEFAULT_OTEL_ENV = "development"
_DEFAULT_OTEL_SERVICE_NAME = "dl-obs"
_DEFAULT_OTEL_SERVICE_NAMESPACE = "dl-obs"
_DEFAULT_OTEL_SERVICE_VERSION = "0.1.0"


@lru_cache(maxsize=8)
def _read_config_file(config_path: str = "configs/config.yaml") -> dict[str, Any]:
    with open(config_path) as file:
        config = yaml.safe_load(file)
    return config if config is not None else {}


def load_storage_type() -> str:
    config = _read_config_file()
    storage_config = config.get("storage", {})

    storage_type = (
        "azure" if "azure" in storage_config else "s3" if "s3" in storage_config else None
    )
    if storage_type is None:
        raise ValueError(
            "No storage configuration found in config.yaml under 'storage.azure' or 'storage.s3'"
        )

    return storage_type


def _env(name: str) -> str | None:
    return os.environ.get(name)


def _resolve_env_reference(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("$"):
        return _env(value[1:])
    return str(value)


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value is not None and value.strip() != "":
            return value
    return None


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None or value.strip() == "":
        raise ValueError(f"Missing required configuration value: {field_name}")
    return value


class AzureSettings(BaseModel):
    connection_string: str
    container_name: str
    account_name: str | None = None
    file_prefix: str = DEFAULT_AZ_FILE_PREFIX
    file_identifier: str = DEFAULT_AZ_FILE_IDENTIFIER
    file_extension: str = DEFAULT_AZ_FILE_EXTENSION
    chunk_folder: str = "chunks"
    models_folder: str = "models"


class LimitsSettings(BaseModel):
    offset_days: int = DEFAULTS_LIMITS_OFFSET_DAYS
    training_window_days: int = DEFAULTS_LIMITS_TRAINING_WINDOW_DAYS
    training_test_size: float = DEFAULTS_LIMITS_DF_SPLIT_SIZE
    training_val_size: float = DEFAULTS_LIMITS_DF_SPLIT_SIZE
    target_column_name: str = DEFAULT_LIMITS_TARGET_COL_NAME


class S3Settings(BaseModel):
    bucket_name: str
    region_name: str | None = None
    endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    file_prefix: str = DEFAULT_S3_FILE_PREFIX
    file_identifier: str = DEFAULT_S3_FILE_IDENTIFIER
    file_extension: str = DEFAULT_S3_FILE_EXTENSION
    chunk_folder: str = "chunks"
    models_folder: str = "models"


class LogsSettings(BaseModel):
    log_level: str = "info"


class RandomForestSettings(BaseModel):
    enabled: bool = False
    n_estimators: int = 100
    max_depth: int = 10
    min_samples_split: int = 10
    random_state: int = 42
    n_jobs: int = -1
    verbose: int = 0


class XGBoostSettings(BaseModel):
    enabled: bool = False
    n_estimators: int = 300
    max_depth: int = 6
    learning_rate: float = 0.05
    subsample: float = 0.9
    colsample_bytree: float = 0.9
    min_child_weight: float = 1.0
    gamma: float = 0.0
    reg_alpha: float = 0.0
    reg_lambda: float = 1.0
    random_state: int = 42
    n_jobs: int = -1
    verbosity: int = 0


class ProphetSettings(BaseModel):
    enabled: bool = False
    seasonality_mode: str = "additive"
    changepoint_prior_scale: float = 0.05
    seasonality_prior_scale: float = 10.0
    yearly_seasonality: bool = False
    weekly_seasonality: bool = True
    daily_seasonality: bool = True


class PytorchSettings(BaseModel):
    enabled: bool = False
    device: str = "auto"
    ensemble_runs: int = 1
    sequence_length: int = 60
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2
    learning_rate: float = 0.001
    weight_decay: float = 0.0
    batch_size: int = 128
    epochs: int = 20
    early_stopping_patience: int = 5
    random_seed: int = 42


class ModelSettings(BaseModel):
    random_forest: RandomForestSettings = RandomForestSettings()
    xgboost: XGBoostSettings = XGBoostSettings()
    prophet: ProphetSettings = ProphetSettings()
    pytorch: PytorchSettings = PytorchSettings()


class KafkaSettings(BaseModel):
    broker: str
    topic: str
    group_id: str


class PolarisSettings(BaseModel):
    url: str
    token: str


class PostgresSettings(BaseModel):
    connection_string: str
    ssl_enabled: bool = False


class IcebergSettings(BaseModel):
    catalog_name: str
    database_name: str
    warehouse_path: str = "warehouse"
    namespace: str | None = None
    table_name: str | None = None
    polaris: PolarisSettings | None = None
    postgres: PostgresSettings | None = None


class MetricFilterSettings(BaseModel):
    name: str
    resource_attributes: dict[str, str] = {}
    attributes: dict[str, str] = {}


class MetricsSettings(BaseModel):
    include: list[MetricFilterSettings] = []


class LogFilterSettings(BaseModel):
    service_name: str | None = None
    level: str | None = None
    contains: str | None = None


class LogsIntegrationSettings(BaseModel):
    include: list[LogFilterSettings] = []


class QueryEntry(BaseModel):
    id: str
    query: str
    resource_attributes: dict[str, str] = {}


class ProducerQueriesSettings(BaseModel):
    prometheus: dict[str, list[QueryEntry]] = {}
    loki: dict[str, list[QueryEntry]] = {}


class ProducerSettings(BaseModel):
    scrape_interval_min: int = 1
    queries: ProducerQueriesSettings = ProducerQueriesSettings()


class IntegrationSettings(BaseModel):
    batch_size: int = 1000
    producer: ProducerSettings = ProducerSettings()
    kafka: KafkaSettings
    iceberg: IcebergSettings
    metrics: MetricsSettings = MetricsSettings()
    logs: LogsIntegrationSettings = LogsIntegrationSettings()


class GrafanaSettings(BaseModel):
    url: str
    api_key: str


class TelemetrySettings(BaseModel):
    otlp_endpoint: str = _DEFAULT_OTLP_ENDPOINT
    env: str = _DEFAULT_OTEL_ENV
    service_name: str = _DEFAULT_OTEL_SERVICE_NAME
    service_namespace: str = _DEFAULT_OTEL_SERVICE_NAMESPACE
    service_version: str = _DEFAULT_OTEL_SERVICE_VERSION


def load_logs_settings(config: dict[str, Any] | None = None) -> LogsSettings:
    logs_config: dict[str, Any]
    if config is None:
        project_config = _read_config_file()
        logs_config = project_config.get("log", {})
    elif "log" in config:
        logs_config = config.get("log", {})
    else:
        logs_config = config

    log_level = _first_non_empty(
        _resolve_env_reference(logs_config.get("level")),
        _env("LOG_LEVEL"),
        "info",
    )

    return LogsSettings(log_level=_require_non_empty(log_level, "log.level"))


def load_limits_settings(config: dict[str, Any] | None = None) -> LimitsSettings:
    limits_config: dict[str, Any]
    if config is None:
        project_config = _read_config_file()
        limits_config = project_config.get("limits", {})
    elif "limits" in config:
        limits_config = config.get("limits", {})
    else:
        limits_config = config

    offset_days = limits_config.get("offset_days", DEFAULTS_LIMITS_OFFSET_DAYS)
    training_window_days = limits_config.get(
        "training_window_days", DEFAULTS_LIMITS_TRAINING_WINDOW_DAYS
    )
    training_test_size = limits_config.get("training_test_size", DEFAULTS_LIMITS_DF_SPLIT_SIZE)
    training_val_size = limits_config.get("training_val_size", DEFAULTS_LIMITS_DF_SPLIT_SIZE)
    target_column_name = limits_config.get("target_column_name", DEFAULT_LIMITS_TARGET_COL_NAME)
    return LimitsSettings(
        offset_days=offset_days,
        training_window_days=training_window_days,
        training_test_size=training_test_size,
        training_val_size=training_val_size,
        target_column_name=target_column_name,
    )


def load_model_settings(config: dict[str, Any] | None = None) -> ModelSettings:
    model_config: dict[str, Any]
    if config is None:
        project_config = _read_config_file()
        model_config = project_config.get("models") or project_config.get("model", {})
    elif "models" in config or "model" in config:
        model_config = config.get("models") or config.get("model", {})
    else:
        model_config = config

    rf_config = model_config.get("random_forest", {})
    random_forest_settings = RandomForestSettings(
        enabled=rf_config.get("enabled", False),
        n_estimators=rf_config.get("n_estimators", 100),
        max_depth=rf_config.get("max_depth", 10),
        min_samples_split=rf_config.get("min_samples_split", 10),
        random_state=rf_config.get("random_state", 42),
        n_jobs=rf_config.get("n_jobs", -1),
        verbose=rf_config.get("verbose", 0),
    )

    xgb_config = model_config.get("xgboost", {})
    xgboost_settings = XGBoostSettings(
        enabled=xgb_config.get("enabled", False),
        n_estimators=xgb_config.get("n_estimators", 300),
        max_depth=xgb_config.get("max_depth", 6),
        learning_rate=xgb_config.get("learning_rate", 0.05),
        subsample=xgb_config.get("subsample", 0.9),
        colsample_bytree=xgb_config.get("colsample_bytree", 0.9),
        min_child_weight=xgb_config.get("min_child_weight", 1.0),
        gamma=xgb_config.get("gamma", 0.0),
        reg_alpha=xgb_config.get("reg_alpha", 0.0),
        reg_lambda=xgb_config.get("reg_lambda", 1.0),
        random_state=xgb_config.get("random_state", 42),
        n_jobs=xgb_config.get("n_jobs", -1),
        verbosity=xgb_config.get("verbosity", 0),
    )

    prophet_config = model_config.get("prophet", {})
    prophet_settings = ProphetSettings(
        enabled=prophet_config.get("enabled", False),
        seasonality_mode=prophet_config.get("seasonality_mode", "additive"),
        changepoint_prior_scale=prophet_config.get("changepoint_prior_scale", 0.05),
        seasonality_prior_scale=prophet_config.get("seasonality_prior_scale", 10.0),
        yearly_seasonality=prophet_config.get("yearly_seasonality", False),
        weekly_seasonality=prophet_config.get("weekly_seasonality", True),
        daily_seasonality=prophet_config.get("daily_seasonality", True),
    )

    pytorch_config = model_config.get("pytorch", {})
    pytorch_settings = PytorchSettings(
        enabled=pytorch_config.get("enabled", False),
        device=pytorch_config.get("device", "auto"),
        ensemble_runs=pytorch_config.get("ensemble_runs", 1),
        sequence_length=pytorch_config.get("sequence_length", 60),
        hidden_size=pytorch_config.get("hidden_size", 64),
        num_layers=pytorch_config.get("num_layers", 2),
        dropout=pytorch_config.get("dropout", 0.2),
        learning_rate=pytorch_config.get("learning_rate", 0.001),
        weight_decay=pytorch_config.get("weight_decay", 0.0),
        batch_size=pytorch_config.get("batch_size", 128),
        epochs=pytorch_config.get("epochs", 20),
        early_stopping_patience=pytorch_config.get("early_stopping_patience", 5),
        random_seed=pytorch_config.get("random_seed", 42),
    )

    return ModelSettings(
        random_forest=random_forest_settings,
        xgboost=xgboost_settings,
        prophet=prophet_settings,
        pytorch=pytorch_settings,
    )


def load_integration_settings(config: dict[str, Any] | None = None) -> IntegrationSettings:
    integration_config: dict[str, Any]
    if config is None:
        project_config = _read_config_file()
        integration_config = project_config.get("integration", {})
    elif "integration" in config:
        integration_config = config.get("integration", {})
    else:
        integration_config = config

    kafka_config = integration_config.get("kafka", {})
    kafka_settings = KafkaSettings(
        broker=_require_non_empty(
            _first_non_empty(
                _resolve_env_reference(kafka_config.get("broker")),
                _env("KAFKA_BROKER"),
            ),
            "integration.kafka.broker",
        ),
        topic=_require_non_empty(
            _first_non_empty(
                _resolve_env_reference(kafka_config.get("topic")),
                _env("KAFKA_TOPIC"),
            ),
            "integration.kafka.topic",
        ),
        group_id=_require_non_empty(
            _first_non_empty(
                _resolve_env_reference(kafka_config.get("group_id")),
                _env("KAFKA_GROUP_ID"),
            ),
            "integration.kafka.group_id",
        ),
    )

    iceberg_config = integration_config.get("iceberg", {})
    polaris_config = iceberg_config.get("polaris")
    polaris_settings: PolarisSettings | None = None
    if polaris_config is not None:
        polaris_settings = PolarisSettings(
            url=_require_non_empty(
                _resolve_env_reference(polaris_config.get("url")),
                "integration.iceberg.polaris.url",
            ),
            token=_require_non_empty(
                _resolve_env_reference(polaris_config.get("token")),
                "integration.iceberg.polaris.token",
            ),
        )
    postgres_config = iceberg_config.get("postgres")
    postgres_settings: PostgresSettings | None = None
    if postgres_config is not None:
        postgres_settings = PostgresSettings(
            connection_string=_require_non_empty(
                _resolve_env_reference(postgres_config.get("connection_string")),
                "integration.iceberg.postgres.connection_string",
            ),
            ssl_enabled=postgres_config.get("ssl_enabled", False),
        )
    iceberg_settings = IcebergSettings(
        catalog_name=_require_non_empty(
            iceberg_config.get("catalog_name"), "integration.iceberg.catalog_name"
        ),
        database_name=_require_non_empty(
            iceberg_config.get("database_name"), "integration.iceberg.database_name"
        ),
        namespace=iceberg_config.get("namespace"),
        table_name=iceberg_config.get("table_name"),
        warehouse_path=iceberg_config.get("warehouse_path", "warehouse"),
        polaris=polaris_settings,
        postgres=postgres_settings,
    )

    batch_size = integration_config.get("batch_size", 1000)

    producer_config: dict = integration_config.get("producer") or {}
    queries_config: dict = producer_config.get("queries") or {}
    producer_settings = ProducerSettings(
        scrape_interval_min=producer_config.get("scrape_interval_min", 1),
        queries=ProducerQueriesSettings(
            prometheus={
                ds: [
                    QueryEntry(
                        id=q["id"],
                        query=q["query"],
                        resource_attributes=q.get("resource_attributes") or {},
                    )
                    for q in qs
                ]
                for ds, qs in (queries_config.get("prometheus") or {}).items()
            },
            loki={
                ds: [
                    QueryEntry(
                        id=q["id"],
                        query=q["query"],
                        resource_attributes=q.get("resource_attributes") or {},
                    )
                    for q in qs
                ]
                for ds, qs in (queries_config.get("loki") or {}).items()
            },
        ),
    )

    metrics_raw: list[dict] = (integration_config.get("metrics") or {}).get("include") or []
    metrics_settings = MetricsSettings(
        include=[
            MetricFilterSettings(
                name=_require_non_empty(m.get("name"), "integration.metrics.include[].name"),
                resource_attributes=m.get("resource_attributes") or {},
                attributes=m.get("attributes") or {},
            )
            for m in metrics_raw
        ]
    )

    logs_raw: list[dict] = (integration_config.get("logs") or {}).get("include") or []
    logs_settings = LogsIntegrationSettings(
        include=[
            LogFilterSettings(
                service_name=log.get("service_name"),
                level=log.get("level"),
                contains=log.get("contains"),
            )
            for log in logs_raw
        ]
    )

    return IntegrationSettings(
        batch_size=batch_size,
        producer=producer_settings,
        kafka=kafka_settings,
        iceberg=iceberg_settings,
        metrics=metrics_settings,
        logs=logs_settings,
    )


def load_grafana_settings(config: dict[str, Any] | None = None) -> GrafanaSettings:
    grafana_config: dict[str, Any]
    if config is None:
        project_config = _read_config_file()
        grafana_config = project_config.get("grafana", {})
    elif "grafana" in config:
        grafana_config = config.get("grafana", {})
    else:
        grafana_config = config

    url = _first_non_empty(
        _resolve_env_reference(grafana_config.get("url")),
        _env("GRAFANA_URL"),
    )
    api_key = _first_non_empty(
        _resolve_env_reference(grafana_config.get("api_key")),
        _env("GRAFANA_API_KEY"),
    )

    return GrafanaSettings(
        url=_require_non_empty(url, "grafana.url"),
        api_key=_require_non_empty(api_key, "grafana.api_key"),
    )


def load_azure_settings(config: dict[str, Any] | None = None) -> AzureSettings:
    azure_config: dict[str, Any]
    if config is None:
        project_config = _read_config_file()
        azure_config = project_config.get("storage", {}).get("azure", {})
    elif "storage" in config:
        azure_config = config.get("storage", {}).get("azure", {})
    else:
        azure_config = config

    connection_string = _first_non_empty(
        _resolve_env_reference(azure_config.get("connection_string")),
        _env("AZURE_STORAGE_CONNECTION_STRING"),
    )
    container_name = _first_non_empty(
        _resolve_env_reference(azure_config.get("container_name")),
        _env("AZURE_STORAGE_CONTAINER_NAME"),
    )
    account_name = _first_non_empty(
        _resolve_env_reference(azure_config.get("account_name")),
        _env("AZURE_STORAGE_ACCOUNT_NAME"),
    )

    return AzureSettings(
        connection_string=_require_non_empty(
            connection_string,
            "storage.azure.connection_string",
        ),
        container_name=_require_non_empty(container_name, "storage.azure.container_name"),
        account_name=account_name,
        file_prefix=azure_config.get("file_prefix", DEFAULT_AZ_FILE_PREFIX),
        file_identifier=azure_config.get("file_identifier", DEFAULT_AZ_FILE_IDENTIFIER),
        file_extension=azure_config.get("file_extension", DEFAULT_AZ_FILE_EXTENSION),
        chunk_folder=azure_config.get("chunk_folder", "chunks"),
        models_folder=azure_config.get("models_folder", "models"),
    )


def load_s3_settings(config: dict[str, Any] | None = None) -> S3Settings:
    s3_config: dict[str, Any]
    if config is None:
        project_config = _read_config_file()
        s3_config = project_config.get("storage", {}).get("s3", {})
    elif "storage" in config:
        s3_config = config.get("storage", {}).get("s3", {})
    else:
        s3_config = config

    bucket_name = _first_non_empty(
        _resolve_env_reference(s3_config.get("bucket_name")),
        _env("AWS_S3_BUCKET_NAME"),
        _env("S3_BUCKET_NAME"),
    )
    region_name = _first_non_empty(
        _resolve_env_reference(s3_config.get("region_name") or s3_config.get("region")),
        _env("AWS_S3_REGION"),
        _env("AWS_DEFAULT_REGION"),
    )
    endpoint_url = _first_non_empty(
        _resolve_env_reference(s3_config.get("endpoint_url")),
        _env("AWS_S3_ENDPOINT_URL"),
    )
    aws_access_key_id = _first_non_empty(
        _resolve_env_reference(s3_config.get("aws_access_key_id")),
        _env("AWS_ACCESS_KEY_ID"),
    )
    aws_secret_access_key = _first_non_empty(
        _resolve_env_reference(s3_config.get("aws_secret_access_key")),
        _env("AWS_SECRET_ACCESS_KEY"),
    )
    aws_session_token = _first_non_empty(
        _resolve_env_reference(s3_config.get("aws_session_token")),
        _env("AWS_SESSION_TOKEN"),
    )

    return S3Settings(
        bucket_name=_require_non_empty(bucket_name, "storage.s3.bucket_name"),
        region_name=region_name,
        endpoint_url=endpoint_url,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_session_token=aws_session_token,
        file_prefix=s3_config.get("file_prefix", DEFAULT_S3_FILE_PREFIX),
        file_identifier=s3_config.get("file_identifier", DEFAULT_S3_FILE_IDENTIFIER),
        file_extension=s3_config.get("file_extension", DEFAULT_S3_FILE_EXTENSION),
        chunk_folder=s3_config.get("chunk_folder", "chunks"),
        models_folder=s3_config.get("models_folder", "models"),
    )


def load_storage_settings(config: dict[str, Any] | None = None) -> AzureSettings | S3Settings:
    if config is None:
        project_config = _read_config_file()
        storage_config = project_config.get("storage", {})
    elif "storage" in config:
        storage_config = config.get("storage", {})
    else:
        storage_config = config

    if "azure" in storage_config:
        return load_azure_settings({"storage": storage_config})
    if "s3" in storage_config:
        return load_s3_settings({"storage": storage_config})
    raise ValueError(
        "No storage configuration found in config.yaml under 'storage.azure' or 'storage.s3'"
    )


def load_telemetry_settings(
    otlp_endpoint: str | None = None,
    config: dict[str, Any] | None = None,
) -> TelemetrySettings:
    telemetry_config: dict[str, Any]
    if config is None:
        project_config = _read_config_file()
        telemetry_config = project_config.get("telemetry", {})
    elif "telemetry" in config:
        telemetry_config = config.get("telemetry", {})
    else:
        telemetry_config = config

    endpoint = _first_non_empty(
        otlp_endpoint,
        _resolve_env_reference(telemetry_config.get("otlp_endpoint")),
        _resolve_env_reference(telemetry_config.get("endpoint")),
        _env("OTEL_EXPORTER_OTLP_ENDPOINT"),
        _DEFAULT_OTLP_ENDPOINT,
    )
    env = _first_non_empty(
        _resolve_env_reference(telemetry_config.get("env")),
        _env("OTEL_ENV"),
        _DEFAULT_OTEL_ENV,
    )
    service_name = _first_non_empty(
        _resolve_env_reference(telemetry_config.get("service_name")),
        _env("OTEL_SERVICE_NAME"),
        _DEFAULT_OTEL_SERVICE_NAME,
    )
    service_namespace = _first_non_empty(
        _resolve_env_reference(telemetry_config.get("service_namespace")),
        _env("OTEL_SERVICE_NAMESPACE"),
        _DEFAULT_OTEL_SERVICE_NAMESPACE,
    )
    service_version = _first_non_empty(
        _resolve_env_reference(telemetry_config.get("service_version")),
        _env("OTEL_SERVICE_VERSION"),
        _DEFAULT_OTEL_SERVICE_VERSION,
    )

    return TelemetrySettings(
        otlp_endpoint=endpoint or _DEFAULT_OTLP_ENDPOINT,
        env=env or _DEFAULT_OTEL_ENV,
        service_name=service_name or _DEFAULT_OTEL_SERVICE_NAME,
        service_namespace=service_namespace or _DEFAULT_OTEL_SERVICE_NAMESPACE,
        service_version=service_version or _DEFAULT_OTEL_SERVICE_VERSION,
    )
