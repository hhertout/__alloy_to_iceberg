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

    try:
        integration_settings = load_integration_settings()
        consumer = Consumer(
            {
                "bootstrap.servers": integration_settings.kafka.broker,
                "group.id": integration_settings.kafka.group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,  # commit manuel après flush
            }
        )

        c_client = CatalogClient(integration_settings)
        c_client.load_catalog()
        c_client.create_namespace()
        c_client.create_tables()

        consumer.subscribe([integration_settings.kafka.topic])
        log.info(
            "Kafka consumer initialized and subscribed to topic: %s, consumer group: %s",
            integration_settings.kafka.topic,
            integration_settings.kafka.group_id,
        )

        processor = IntegrationPipelineProcessor(log, integration_settings)
        batch = Batch(log, integration_settings)

        while True:
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
                response = processor.process_message(value)

                # TODO: handle recording rules case
                # for now it only receiving raw opentelemetry metrics, but some recording rules
                # may be integrated in the dataset.
                # It could have his own batch and table, or be processed in the same batch and same
                # table and share the same storage/schema.

                if len(response) > 0:
                    batch.add(response)

                if batch.size >= integration_settings.batch_size:
                    batch.flush(client=c_client)
                    consumer.commit(asynchronous=False)

    except KeyboardInterrupt:
        log.info("Integration pipeline interrupted. Shutting down...")
    except Exception as e:
        log.exception("Unexpected error in integration pipeline: %s", e)
    finally:
        log.info("Integration pipeline finished.")
        if "consumer" in dir():
            consumer.close()
        shutdown_telemetry()


if __name__ == "__main__":
    setup_telemetry()
    main()
