"""Tests targeting uncovered lines in configs/base.py."""

from unittest.mock import patch

import pytest

from configs.base import (
    LogFilterSettings,
    LogsIntegrationSettings,
    PolarisSettings,
    PostgresSettings,
    _first_non_empty,
    _read_config_file,
    _require_non_empty,
    _resolve_env_reference,
    load_azure_settings,
    load_grafana_settings,
    load_integration_settings,
    load_limits_settings,
    load_logs_settings,
    load_model_settings,
    load_s3_settings,
    load_storage_settings,
    load_storage_type,
    load_telemetry_settings,
)

# ---------------------------------------------------------------------------
# Private helpers — lines 36-47, 58, 66, 71
# ---------------------------------------------------------------------------


class TestResolveEnvReference:
    def test_none_returns_none(self) -> None:
        assert _resolve_env_reference(None) is None

    def test_plain_string_returned_as_is(self) -> None:
        assert _resolve_env_reference("hello") == "hello"

    def test_dollar_prefix_reads_env(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_VAR", "secret")
        assert _resolve_env_reference("$MY_VAR") == "secret"

    def test_dollar_prefix_missing_env_returns_none(self, monkeypatch) -> None:
        monkeypatch.delenv("UNSET_VAR_XYZ", raising=False)
        assert _resolve_env_reference("$UNSET_VAR_XYZ") is None

    def test_non_string_value_cast_to_str(self) -> None:
        assert _resolve_env_reference(42) == "42"
        assert _resolve_env_reference(3.14) == "3.14"


class TestFirstNonEmpty:
    def test_returns_first_non_empty(self) -> None:
        assert _first_non_empty(None, "", "  ", "found") == "found"

    def test_all_empty_returns_none(self) -> None:
        assert _first_non_empty(None, "", "   ") is None

    def test_first_value_returned_immediately(self) -> None:
        assert _first_non_empty("first", "second") == "first"

    def test_no_arguments_returns_none(self) -> None:
        assert _first_non_empty() is None


class TestRequireNonEmpty:
    def test_valid_value_returned(self) -> None:
        assert _require_non_empty("ok", "field") == "ok"

    def test_none_raises(self) -> None:
        with pytest.raises(ValueError, match="field.name"):
            _require_non_empty(None, "field.name")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="field.name"):
            _require_non_empty("", "field.name")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="field.name"):
            _require_non_empty("   ", "field.name")


class TestReadConfigFile:
    def test_reads_valid_yaml(self, tmp_path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("key: value\nnumber: 42\n")
        _read_config_file.cache_clear()
        result = _read_config_file(str(cfg))
        assert result == {"key": "value", "number": 42}
        _read_config_file.cache_clear()

    def test_empty_yaml_returns_empty_dict(self, tmp_path) -> None:
        cfg = tmp_path / "empty.yaml"
        cfg.write_text("")
        _read_config_file.cache_clear()
        result = _read_config_file(str(cfg))
        assert result == {}
        _read_config_file.cache_clear()


# ---------------------------------------------------------------------------
# load_storage_type — lines 36-47
# ---------------------------------------------------------------------------


class TestLoadStorageType:
    def test_azure_detected(self) -> None:
        with patch("configs.base._read_config_file", return_value={"storage": {"azure": {}}}):
            assert load_storage_type() == "azure"

    def test_s3_detected(self) -> None:
        with patch("configs.base._read_config_file", return_value={"storage": {"s3": {}}}):
            assert load_storage_type() == "s3"

    def test_no_storage_raises(self) -> None:
        with (
            patch("configs.base._read_config_file", return_value={"storage": {}}),
            pytest.raises(ValueError, match="No storage configuration"),
        ):
            load_storage_type()


# ---------------------------------------------------------------------------
# load_logs_settings — lines 217-220
# ---------------------------------------------------------------------------


class TestLoadLogsSettings:
    def test_with_log_key_in_dict(self) -> None:
        s = load_logs_settings({"log": {"level": "debug"}})
        assert s.log_level == "debug"

    def test_with_direct_dict(self) -> None:
        s = load_logs_settings({"level": "warn"})
        assert s.log_level == "warn"

    def test_env_var_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "error")
        s = load_logs_settings({"level": None})
        assert s.log_level == "error"
        monkeypatch.delenv("LOG_LEVEL")

    def test_default_is_info(self) -> None:
        s = load_logs_settings({})
        assert s.log_level == "info"


# ---------------------------------------------------------------------------
# load_limits_settings — lines 233-248
# ---------------------------------------------------------------------------


class TestLoadLimitsSettings:
    def test_with_limits_key(self) -> None:
        s = load_limits_settings({"limits": {"offset_days": 3, "training_window_days": 10}})
        assert s.offset_days == 3
        assert s.training_window_days == 10

    def test_with_direct_dict(self) -> None:
        s = load_limits_settings({"offset_days": 5})
        assert s.offset_days == 5

    def test_defaults(self) -> None:
        s = load_limits_settings({})
        assert s.training_test_size == 0.15
        assert s.training_val_size == 0.15
        assert s.target_column_name == "target"


# ---------------------------------------------------------------------------
# load_model_settings — lines 260-261, 265
# ---------------------------------------------------------------------------


class TestLoadModelSettingsExtra:
    def test_model_key_fallback(self) -> None:
        """Should accept 'model' (singular) as well as 'models'."""
        s = load_model_settings({"model": {"random_forest": {"enabled": True}}})
        assert s.random_forest.enabled is True

    def test_direct_dict(self) -> None:
        s = load_model_settings({"random_forest": {"enabled": True, "n_estimators": 77}})
        assert s.random_forest.n_estimators == 77

    def test_defaults_when_empty(self) -> None:
        s = load_model_settings({})
        assert s.random_forest.enabled is False
        assert s.xgboost.enabled is False
        assert s.prophet.enabled is False
        assert s.pytorch.enabled is False


# ---------------------------------------------------------------------------
# load_integration_settings — lines 333-375
# ---------------------------------------------------------------------------

_KAFKA = {"broker": "localhost:19092", "topic": "test", "group_id": "grp"}
_ICEBERG = {"catalog_name": "cat", "database_name": "db", "table_name": "tbl"}


class TestLoadIntegrationSettings:
    def test_minimal_config(self) -> None:
        s = load_integration_settings({"kafka": _KAFKA, "iceberg": _ICEBERG})
        assert s.kafka.broker == "localhost:19092"
        assert s.iceberg.table_name == "tbl"
        assert s.batch_size == 1000
        assert s.metrics.include == []

    def test_namespace_parsed(self) -> None:
        s = load_integration_settings(
            {"kafka": _KAFKA, "iceberg": {**_ICEBERG, "namespace": "obs"}}
        )
        assert s.iceberg.namespace == "obs"

    def test_namespace_defaults_to_none(self) -> None:
        s = load_integration_settings({"kafka": _KAFKA, "iceberg": _ICEBERG})
        assert s.iceberg.namespace is None

    def test_with_integration_key(self) -> None:
        s = load_integration_settings({"integration": {"kafka": _KAFKA, "iceberg": _ICEBERG}})
        assert s.kafka.topic == "test"

    def test_batch_size_override(self) -> None:
        s = load_integration_settings({"kafka": _KAFKA, "iceberg": _ICEBERG, "batch_size": 500})
        assert s.batch_size == 500

    def test_metrics_include(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": _ICEBERG,
            "metrics": {
                "include": [
                    {
                        "name": "cpu_usage",
                        "resource_attributes": {"service.name": "app"},
                        "attributes": {"env": "prod"},
                    },
                ]
            },
        }
        s = load_integration_settings(cfg)
        assert len(s.metrics.include) == 1
        assert s.metrics.include[0].name == "cpu_usage"
        assert s.metrics.include[0].resource_attributes == {"service.name": "app"}
        assert s.metrics.include[0].attributes == {"env": "prod"}

    def test_missing_kafka_broker_raises(self) -> None:
        with pytest.raises(ValueError, match="integration.kafka.broker"):
            load_integration_settings(
                {"kafka": {"topic": "t", "group_id": "g"}, "iceberg": _ICEBERG}
            )

    def test_kafka_env_var_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("KAFKA_BROKER", "env-broker:9092")
        monkeypatch.setenv("KAFKA_TOPIC", "env-topic")
        monkeypatch.setenv("KAFKA_GROUP_ID", "env-group")
        s = load_integration_settings({"kafka": {}, "iceberg": _ICEBERG})
        assert s.kafka.broker == "env-broker:9092"
        assert s.kafka.topic == "env-topic"
        assert s.kafka.group_id == "env-group"

    def test_kafka_dollar_env_reference(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_BROKER", "ref-broker:9092")
        s = load_integration_settings(
            {"kafka": {"broker": "$MY_BROKER", "topic": "t", "group_id": "g"}, "iceberg": _ICEBERG}
        )
        assert s.kafka.broker == "ref-broker:9092"

    def test_missing_iceberg_table_is_none(self) -> None:
        s = load_integration_settings(
            {"kafka": _KAFKA, "iceberg": {"catalog_name": "c", "database_name": "d"}}
        )
        assert s.iceberg.table_name is None

    def test_polaris_defaults_to_none(self) -> None:
        s = load_integration_settings({"kafka": _KAFKA, "iceberg": _ICEBERG})
        assert s.iceberg.polaris is None

    def test_polaris_parsed(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": {**_ICEBERG, "polaris": {"url": "http://polaris", "token": "tok"}},
        }
        s = load_integration_settings(cfg)
        assert s.iceberg.polaris is not None
        assert s.iceberg.polaris.url == "http://polaris"
        assert s.iceberg.polaris.token == "tok"

    def test_polaris_env_var_resolved(self, monkeypatch) -> None:
        monkeypatch.setenv("POLARIS_URL", "http://env-polaris")
        monkeypatch.setenv("POLARIS_TOKEN", "env-tok")
        cfg = {
            "kafka": _KAFKA,
            "iceberg": {**_ICEBERG, "polaris": {"url": "$POLARIS_URL", "token": "$POLARIS_TOKEN"}},
        }
        s = load_integration_settings(cfg)
        assert s.iceberg.polaris.url == "http://env-polaris"
        assert s.iceberg.polaris.token == "env-tok"

    def test_polaris_missing_url_raises(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": {**_ICEBERG, "polaris": {"token": "tok"}},
        }
        with pytest.raises(ValueError, match="integration.iceberg.polaris.url"):
            load_integration_settings(cfg)

    def test_polaris_missing_token_raises(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": {**_ICEBERG, "polaris": {"url": "http://polaris"}},
        }
        with pytest.raises(ValueError, match="integration.iceberg.polaris.token"):
            load_integration_settings(cfg)

    def test_postgres_defaults_to_none(self) -> None:
        s = load_integration_settings({"kafka": _KAFKA, "iceberg": _ICEBERG})
        assert s.iceberg.postgres is None

    def test_postgres_parsed(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": {
                **_ICEBERG,
                "postgres": {
                    "connection_string": "postgresql://user:pass@localhost:5432/db",
                    "ssl_enabled": True,
                },
            },
        }
        s = load_integration_settings(cfg)
        assert s.iceberg.postgres is not None
        assert s.iceberg.postgres.connection_string == "postgresql://user:pass@localhost:5432/db"
        assert s.iceberg.postgres.ssl_enabled is True

    def test_postgres_ssl_defaults_to_false(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": {
                **_ICEBERG,
                "postgres": {"connection_string": "postgresql://localhost/db"},
            },
        }
        s = load_integration_settings(cfg)
        assert s.iceberg.postgres.ssl_enabled is False

    def test_postgres_env_var_resolved(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_CONN", "postgresql://env-host/db")
        cfg = {
            "kafka": _KAFKA,
            "iceberg": {
                **_ICEBERG,
                "postgres": {"connection_string": "$PG_CONN"},
            },
        }
        s = load_integration_settings(cfg)
        assert s.iceberg.postgres.connection_string == "postgresql://env-host/db"

    def test_postgres_missing_connection_string_raises(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": {**_ICEBERG, "postgres": {}},
        }
        with pytest.raises(ValueError, match="integration.iceberg.postgres.connection_string"):
            load_integration_settings(cfg)

    def test_logs_defaults_to_empty(self) -> None:
        s = load_integration_settings({"kafka": _KAFKA, "iceberg": _ICEBERG})
        assert s.logs.include == []

    def test_logs_include_parsed(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": _ICEBERG,
            "logs": {
                "include": [
                    {"service_name": "redpanda", "level": "info", "contains": ".*ml_obs.*"},
                ]
            },
        }
        s = load_integration_settings(cfg)
        assert len(s.logs.include) == 1
        assert s.logs.include[0].service_name == "redpanda"
        assert s.logs.include[0].level == "info"
        assert s.logs.include[0].contains == ".*ml_obs.*"

    def test_logs_multiple_filters(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": _ICEBERG,
            "logs": {
                "include": [
                    {"service_name": "redpanda", "level": "error"},
                    {"contains": "timeout"},
                ]
            },
        }
        s = load_integration_settings(cfg)
        assert len(s.logs.include) == 2
        assert s.logs.include[1].service_name is None
        assert s.logs.include[1].contains == "timeout"

    def test_logs_partial_fields_are_none(self) -> None:
        cfg = {
            "kafka": _KAFKA,
            "iceberg": _ICEBERG,
            "logs": {"include": [{"service_name": "app"}]},
        }
        s = load_integration_settings(cfg)
        f = s.logs.include[0]
        assert f.service_name == "app"
        assert f.level is None
        assert f.contains is None


# ---------------------------------------------------------------------------
# LogFilterSettings model
# ---------------------------------------------------------------------------


class TestLogFilterSettings:
    def test_all_fields_optional(self) -> None:
        f = LogFilterSettings()
        assert f.service_name is None
        assert f.level is None
        assert f.contains is None

    def test_set_all_fields(self) -> None:
        f = LogFilterSettings(service_name="svc", level="warn", contains="error.*")
        assert f.service_name == "svc"
        assert f.level == "warn"
        assert f.contains == "error.*"


class TestLogsIntegrationSettings:
    def test_empty_include_by_default(self) -> None:
        s = LogsIntegrationSettings()
        assert s.include == []

    def test_include_list(self) -> None:
        s = LogsIntegrationSettings(
            include=[LogFilterSettings(service_name="a"), LogFilterSettings(level="debug")]
        )
        assert len(s.include) == 2
        assert s.include[0].service_name == "a"
        assert s.include[1].level == "debug"


class TestPolarisSettings:
    def test_basic(self) -> None:
        p = PolarisSettings(url="http://polaris", token="mytoken")
        assert p.url == "http://polaris"
        assert p.token == "mytoken"


class TestPostgresSettings:
    def test_basic(self) -> None:
        p = PostgresSettings(connection_string="postgresql://localhost/db")
        assert p.connection_string == "postgresql://localhost/db"
        assert p.ssl_enabled is False

    def test_ssl_enabled(self) -> None:
        p = PostgresSettings(connection_string="postgresql://localhost/db", ssl_enabled=True)
        assert p.ssl_enabled is True


# ---------------------------------------------------------------------------
# load_grafana_settings — lines 385-402
# ---------------------------------------------------------------------------


class TestLoadGrafanaSettings:
    def test_basic(self) -> None:
        s = load_grafana_settings({"url": "http://localhost:3000", "api_key": "abc"})
        assert s.url == "http://localhost:3000"
        assert s.api_key == "abc"

    def test_with_grafana_key(self) -> None:
        s = load_grafana_settings({"grafana": {"url": "http://g:3000", "api_key": "tok"}})
        assert s.url == "http://g:3000"

    def test_env_var_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("GRAFANA_URL", "http://env:3000")
        monkeypatch.setenv("GRAFANA_API_KEY", "envkey")
        s = load_grafana_settings({})
        assert s.url == "http://env:3000"
        assert s.api_key == "envkey"

    def test_dollar_env_reference(self, monkeypatch) -> None:
        monkeypatch.setenv("GRAFANA_SA_TOKEN", "mytoken")
        s = load_grafana_settings({"url": "http://localhost:3000", "api_key": "$GRAFANA_SA_TOKEN"})
        assert s.api_key == "mytoken"

    def test_missing_url_raises(self) -> None:
        with pytest.raises(ValueError, match="grafana.url"):
            load_grafana_settings({"api_key": "k"})

    def test_missing_api_key_raises(self) -> None:
        with pytest.raises(ValueError, match="grafana.api_key"):
            load_grafana_settings({"url": "http://localhost:3000"})


# ---------------------------------------------------------------------------
# load_azure_settings — lines 410-427
# ---------------------------------------------------------------------------


class TestLoadAzureSettings:
    def test_basic(self) -> None:
        s = load_azure_settings({"connection_string": "cs", "container_name": "cnt"})
        assert s.connection_string == "cs"
        assert s.container_name == "cnt"

    def test_with_storage_key(self) -> None:
        s = load_azure_settings(
            {"storage": {"azure": {"connection_string": "cs", "container_name": "cnt"}}}
        )
        assert s.container_name == "cnt"

    def test_env_var_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "envcs")
        monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "envcnt")
        s = load_azure_settings({})
        assert s.connection_string == "envcs"
        assert s.container_name == "envcnt"

    def test_custom_folders(self) -> None:
        s = load_azure_settings(
            {
                "connection_string": "cs",
                "container_name": "cnt",
                "chunk_folder": "raw",
                "models_folder": "ml",
            }
        )
        assert s.chunk_folder == "raw"
        assert s.models_folder == "ml"

    def test_account_name_defaults_to_none(self) -> None:
        s = load_azure_settings({"connection_string": "cs", "container_name": "cnt"})
        assert s.account_name is None

    def test_account_name_from_config(self) -> None:
        s = load_azure_settings(
            {"connection_string": "cs", "container_name": "cnt", "account_name": "myaccount"}
        )
        assert s.account_name == "myaccount"

    def test_account_name_env_var_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "envaccount")
        s = load_azure_settings({"connection_string": "cs", "container_name": "cnt"})
        assert s.account_name == "envaccount"

    def test_account_name_dollar_ref_resolved(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_ACCT", "refaccount")
        s = load_azure_settings(
            {"connection_string": "cs", "container_name": "cnt", "account_name": "$MY_ACCT"}
        )
        assert s.account_name == "refaccount"

    def test_missing_connection_string_raises(self) -> None:
        with pytest.raises(ValueError, match="storage.azure.connection_string"):
            load_azure_settings({"container_name": "cnt"})

    def test_missing_container_raises(self) -> None:
        with pytest.raises(ValueError, match="storage.azure.container_name"):
            load_azure_settings({"connection_string": "cs"})


# ---------------------------------------------------------------------------
# load_s3_settings — lines 443-478
# ---------------------------------------------------------------------------


class TestLoadS3Settings:
    def test_basic(self) -> None:
        s = load_s3_settings({"bucket_name": "my-bucket"})
        assert s.bucket_name == "my-bucket"
        assert s.region_name is None
        assert s.endpoint_url is None

    def test_with_storage_key(self) -> None:
        s = load_s3_settings({"storage": {"s3": {"bucket_name": "b"}}})
        assert s.bucket_name == "b"

    def test_env_var_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("AWS_S3_BUCKET_NAME", "envbucket")
        monkeypatch.setenv("AWS_S3_REGION", "eu-west-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKI")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        s = load_s3_settings({})
        assert s.bucket_name == "envbucket"
        assert s.region_name == "eu-west-1"
        assert s.aws_access_key_id == "AKI"

    def test_s3_bucket_name_fallback(self, monkeypatch) -> None:
        monkeypatch.delenv("AWS_S3_BUCKET_NAME", raising=False)
        monkeypatch.setenv("S3_BUCKET_NAME", "fallback-bucket")
        s = load_s3_settings({})
        assert s.bucket_name == "fallback-bucket"

    def test_region_from_region_key(self) -> None:
        s = load_s3_settings({"bucket_name": "b", "region": "us-east-1"})
        assert s.region_name == "us-east-1"

    def test_all_optional_fields(self) -> None:
        s = load_s3_settings(
            {
                "bucket_name": "b",
                "endpoint_url": "http://minio:9000",
                "aws_access_key_id": "ak",
                "aws_secret_access_key": "sk",
                "aws_session_token": "st",
            }
        )
        assert s.endpoint_url == "http://minio:9000"
        assert s.aws_session_token == "st"

    def test_missing_bucket_raises(self) -> None:
        with pytest.raises(ValueError, match="storage.s3.bucket_name"):
            load_s3_settings({})


# ---------------------------------------------------------------------------
# load_storage_settings
# ---------------------------------------------------------------------------


class TestLoadStorageSettings:
    def test_returns_azure_settings(self) -> None:
        from configs.base import AzureSettings

        s = load_storage_settings(
            {"storage": {"azure": {"connection_string": "cs", "container_name": "cnt"}}}
        )
        assert isinstance(s, AzureSettings)
        assert s.container_name == "cnt"

    def test_returns_s3_settings(self) -> None:
        from configs.base import S3Settings

        s = load_storage_settings({"storage": {"s3": {"bucket_name": "my-bucket"}}})
        assert isinstance(s, S3Settings)
        assert s.bucket_name == "my-bucket"

    def test_direct_dict_azure(self) -> None:
        from configs.base import AzureSettings

        s = load_storage_settings({"azure": {"connection_string": "cs", "container_name": "cnt"}})
        assert isinstance(s, AzureSettings)

    def test_direct_dict_s3(self) -> None:
        from configs.base import S3Settings

        s = load_storage_settings({"s3": {"bucket_name": "b"}})
        assert isinstance(s, S3Settings)

    def test_no_storage_raises(self) -> None:
        with pytest.raises(ValueError, match="No storage configuration"):
            load_storage_settings({})


# ---------------------------------------------------------------------------
# load_telemetry_settings — lines 501-504
# ---------------------------------------------------------------------------


class TestLoadTelemetrySettings:
    def test_basic(self) -> None:
        s = load_telemetry_settings(
            config={
                "endpoint": "http://otel:4317",
                "service_name": "svc",
                "env": "prod",
                "service_namespace": "ns",
                "service_version": "1.0.0",
            }
        )
        assert s.otlp_endpoint == "http://otel:4317"
        assert s.service_name == "svc"
        assert s.env == "prod"

    def test_with_telemetry_key(self) -> None:
        s = load_telemetry_settings(
            config={
                "telemetry": {
                    "endpoint": "http://otel:4317",
                    "service_name": "svc",
                    "env": "dev",
                    "service_namespace": "ns",
                    "service_version": "0.1",
                }
            }
        )
        assert s.otlp_endpoint == "http://otel:4317"

    def test_otlp_endpoint_argument_takes_priority(self) -> None:
        s = load_telemetry_settings(
            otlp_endpoint="http://override:4317", config={"endpoint": "http://ignored:4317"}
        )
        assert s.otlp_endpoint == "http://override:4317"

    def test_env_var_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://envhost:4317")
        monkeypatch.setenv("OTEL_SERVICE_NAME", "env-svc")
        monkeypatch.setenv("OTEL_ENV", "staging")
        s = load_telemetry_settings(config={})
        assert s.otlp_endpoint == "http://envhost:4317"
        assert s.service_name == "env-svc"
        assert s.env == "staging"

    def test_defaults_when_empty(self) -> None:
        s = load_telemetry_settings(config={})
        assert s.otlp_endpoint == "http://localhost:4317"
        assert s.env == "development"
        assert s.service_name == "dl-obs"

    def test_otlp_endpoint_key(self) -> None:
        """Both 'endpoint' and 'otlp_endpoint' YAML keys should work."""
        s = load_telemetry_settings(config={"otlp_endpoint": "http://alt:4317"})
        assert s.otlp_endpoint == "http://alt:4317"
