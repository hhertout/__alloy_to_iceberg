import datetime
import signal
import socket
from time import sleep
from typing import Any

from confluent_kafka import Producer
from dotenv import load_dotenv
from google.protobuf.json_format import MessageToJson
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest

from configs.base import ProducerQueriesSettings, load_integration_settings
from configs.constants import DatasourceKind
from src.client.grafana import GrafanaDao
from utils.askii_art import print_ascii_art
from utils.grafana_to_otlp import convert_grafana_resp_to_otlp
from utils.logging import get_logger
from utils.telemetry import setup_telemetry, shutdown_telemetry


def get_data(
    queries_settings: ProducerQueriesSettings, interval_min: int, client: GrafanaDao, log: Any
) -> list[ExportMetricsServiceRequest]:
    """Retrieve data from Grafana based on the provided queries and time range."""
    results = []
    for datasource, queries in queries_settings.prometheus.items():
        for entry in queries:
            now = datetime.datetime.now(datetime.UTC)
            from_time = now - datetime.timedelta(minutes=interval_min)
            datasource_uid = client.get_datasource_uid(datasource)

            result = client.query(
                kind=DatasourceKind.PROMETHEUS,
                datasource_uid=datasource_uid,
                expr=entry.query,
                from_time=from_time.timestamp(),
                to_time=now.timestamp(),
            )

            results.append(
                convert_grafana_resp_to_otlp(
                    grafana_response=result,
                    ref_id_to_name=entry.id,
                    resource_attrs=entry.resource_attributes,
                )
            )

    for datasource, queries in queries_settings.loki.items():
        for entry in queries:
            now = datetime.datetime.now(datetime.UTC)
            from_time = now - datetime.timedelta(minutes=interval_min)
            datasource_uid = client.get_datasource_uid(datasource)

            result = client.query(
                kind=DatasourceKind.LOKI,
                datasource_uid=datasource_uid,
                expr=entry.query,
                from_time=from_time.timestamp(),
                to_time=now.timestamp(),
            )

            results.append(
                convert_grafana_resp_to_otlp(
                    grafana_response=result,
                    ref_id_to_name=entry.id,
                    resource_attrs=entry.resource_attributes,
                )
            )

    return results


def main() -> None:
    print_ascii_art()
    log = get_logger("metrics_producer")
    log.info("Starting metrics producer...")
    integration_settings = load_integration_settings()
    conf: dict[str, str | int | float | bool] = {
        "bootstrap.servers": integration_settings.kafka.broker,
        "client.id": socket.gethostname(),
    }
    producer = Producer(conf)

    shutdown = False

    def shutdown_gracefully(signum: int, _: object) -> None:
        nonlocal shutdown
        log.info("Received signal %s, shutting down gracefully...", signal.Signals(signum).name)
        shutdown = True
        producer.flush()
        shutdown_telemetry()
        exit(0)

    signal.signal(signal.SIGTERM, shutdown_gracefully)
    signal.signal(signal.SIGINT, shutdown_gracefully)

    try:
        grafana_client = GrafanaDao()

        while True:
            # retrieve data from Grafana or other sources.
            results = get_data(
                queries_settings=integration_settings.producer.queries,
                interval_min=integration_settings.producer.scrape_interval_min,
                client=grafana_client,
                log=log,
            )

            produced = 0
            for result in results:
                has_data = any(
                    any(len(sm.metrics) > 0 for sm in rm.scope_metrics)
                    for rm in result.resource_metrics
                )
                if not has_data:
                    log.debug("Skipping empty OTLP message")
                    continue
                producer.produce(
                    integration_settings.kafka.topic.metrics, key=None, value=MessageToJson(result)
                )
                produced += 1

            log.info("Produced %d messages to Kafka topic", produced)
            # wait for an interval
            sleep(integration_settings.producer.scrape_interval_min * 60)
    except KeyboardInterrupt:
        log.info("Metrics producer interrupted by user.")
    except Exception as e:
        log.exception("Unexpected error in metrics producer: %s", e)
    finally:
        producer.flush()
        shutdown_telemetry()


if __name__ == "__main__":
    load_dotenv()
    setup_telemetry()
    main()
