package org.example;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.example.factory.LogProcessor;
import org.example.factory.MetricProcessor;
import org.example.serializer.OtlpLogsSerde;
import org.example.serializer.OtlpMetricsSerde;
import org.example.utils.GlobalConfig;
import org.example.utils.IngestionConfig;

import java.util.Properties;
import java.util.concurrent.CountDownLatch;

public class Main {
    private static Properties getProperties(GlobalConfig config) {
        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, config.applicationId());
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, config.bootstrapServers());
        props.put(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG, Serdes.String().getClass().getName());
        props.put(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG, Serdes.String().getClass().getName());
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, config.autoOffsetReset());
        return props;
    }

    public static void main(String[] args) {
        final GlobalConfig config = new GlobalConfig();
        Properties props = getProperties(config);

        final IngestionConfig.Config ingestionConfig = IngestionConfig.loadConfig("./config/config.yaml");

        final StreamsBuilder builder = new StreamsBuilder();
        final MetricProcessor metricProcessor = new MetricProcessor(ingestionConfig);
        final LogProcessor logProcessor = new LogProcessor();

        builder.stream(config.inputMetricTopic(), Consumed.with(Serdes.String(), new OtlpMetricsSerde()))
                .flatMapValues(metricProcessor::process)
                .to(config.outputMetricTopic());

        builder.stream(config.inputLogTopic(), Consumed.with(Serdes.String(), new OtlpLogsSerde()))
                .flatMapValues(logProcessor::process)
                .to(config.outputLogTopic());

        try {
            final CountDownLatch latch = new CountDownLatch(1);
            final Topology topology = builder.build();
            final KafkaStreams streams = new KafkaStreams(topology, props);

            Runtime.getRuntime().addShutdownHook(new Thread("streams-shutdown-hook") {
                @Override
                public void run() {
                    streams.close();
                    latch.countDown();
                }
            });

            streams.start();
            latch.await();
        } catch (Throwable e) {
            System.exit(1);
        }
        System.exit(0);
    }
}