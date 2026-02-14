import os
from functools import lru_cache
from typing import Any

import yaml
from pydantic import BaseModel

from configs.constants import (
    DEFAULT_AZ_FILE_EXTENSION,
    DEFAULT_AZ_FILE_IDENTIFIER,
    DEFAULT_AZ_FILE_PREFIX,
    DEFAULT_S3_FILE_EXTENSION,
    DEFAULT_S3_FILE_IDENTIFIER,
    DEFAULT_S3_FILE_PREFIX,
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


class AzureSettings(BaseModel):
    connection_string: str
    container_name: str
    file_prefix: str = DEFAULT_AZ_FILE_PREFIX
    file_identifier: str = DEFAULT_AZ_FILE_IDENTIFIER
    file_extension: str = DEFAULT_AZ_FILE_EXTENSION
    chunk_folder: str = "chunks"
    models_folder: str = "models"


class LimitsSettings(BaseModel):
    offset_days: int = DEFAULTS_LIMITS_OFFSET_DAYS
    training_window_days: int = DEFAULTS_LIMITS_TRAINING_WINDOW_DAYS


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

    return LogsSettings(log_level=log_level)


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

    return LimitsSettings(offset_days=offset_days, training_window_days=training_window_days)


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

    return GrafanaSettings(url=url, api_key=api_key)


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

    return AzureSettings(
        connection_string=connection_string,
        container_name=container_name,
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
        bucket_name=bucket_name,
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
