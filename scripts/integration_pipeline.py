import signal

from confluent_kafka import Consumer, KafkaError
from dotenv import load_dotenv

from configs.base import (
    load_integration_settings,
)
from src.integration.batch import Batch
from src.integration.catalog import CatalogClient
from src.integration.processor import IntegrationPipelineProcessor
from utils import get_logger
from utils.askii_art import print_ascii_art
from utils.telemetry import setup_telemetry, shutdown_telemetry


def main() -> None:
    load_dotenv()
    print_ascii_art()
    log = get_logger("integration_pipeline")
    log.info("Starting integration pipeline...")

    integration_settings = load_integration_settings()
    consumer = Consumer(
        {
            "bootstrap.servers": integration_settings.kafka.broker,
            "group.id": integration_settings.kafka.group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    batch = Batch(log, integration_settings)
    c_client = CatalogClient(integration_settings)

    shutdown = False

    def shutdown_gracefully(signum: int, _: object) -> None:
        nonlocal shutdown
        log.info("Received signal %s, shutting down gracefully...", signal.Signals(signum).name)
        shutdown = True

    signal.signal(signal.SIGTERM, shutdown_gracefully)
    signal.signal(signal.SIGINT, shutdown_gracefully)

    try:
        c_client.load_catalog()
        c_client.create_namespace()
        c_client.create_tables()

        consumer.subscribe([integration_settings.kafka.topic.metrics, integration_settings.kafka.topic.logs])
        log.info(
            "Kafka consumer initialized and subscribed to topics: %s, consumer group: %s",
            [integration_settings.kafka.topic.metrics, integration_settings.kafka.topic.logs],
            integration_settings.kafka.group_id,
        )

        processor = IntegrationPipelineProcessor(log, integration_settings)

        while not shutdown:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                pass
            elif (kafka_err := msg.error()) is not None:
                if kafka_err.code() != KafkaError._PARTITION_EOF:  # type: ignore[attr-defined]
                    log.error("Kafka error: %s", kafka_err)
            else:
                value = msg.value()
                if value is None:
                    continue

                metrics_df, logs_df = processor.process_message(value)

                if len(metrics_df) > 0:
                    batch.add(metrics_df, kind="metric")

                if len(logs_df) > 0:
                    batch.add(logs_df, kind="log")

                log.debug(f"Batch size: {batch.size_bytes} bytes")
                if batch.size_bytes >= integration_settings.batch_size:
                    batch.flush(client=c_client)
                    consumer.commit(asynchronous=False)

        # Flush remaining data before exit (SIGTERM or normal shutdown)
        if batch.size > 0:
            log.info("Flushing remaining batch (%d rows) before shutdown...", batch.size)
            batch.flush(client=c_client)
            consumer.commit(asynchronous=False)
            log.info("Remaining batch flushed successfully.")

    except KeyboardInterrupt:
        log.info("Integration pipeline interrupted. Shutting down...")
    except Exception as e:
        log.exception("Unexpected error in integration pipeline: %s", e)
    finally:
        log.info("Integration pipeline finished.")
        if batch.size > 0:
            log.info("Flushing remaining batch (%d rows) before shutdown...", batch.size)
            batch.flush(client=c_client)
            consumer.commit(asynchronous=False)
            log.info("Remaining batch flushed successfully.")
        consumer.close()
        shutdown_telemetry()


if __name__ == "__main__":
    setup_telemetry()
    main()
