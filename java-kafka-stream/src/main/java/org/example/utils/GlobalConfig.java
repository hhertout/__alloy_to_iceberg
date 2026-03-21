package org.example.utils;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

/**
 * Loads {@code application.properties} from the classpath and exposes
 * each parameter with a typed accessor and a sensible default value.
 */
public class GlobalConfig {

    private final Properties props;

    public GlobalConfig() {
        props = new Properties();
        try (InputStream is = GlobalConfig.class.getClassLoader()
                                             .getResourceAsStream("application.properties")) {
            if (is == null) {
                throw new IllegalStateException("application.properties not found on classpath");
            }
            props.load(is);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to load application.properties", e);
        }
    }

    // ── Kafka broker ─────────────────────────────────────────────────────────────

    public String bootstrapServers() {
        return get("kafka.bootstrap.servers", "localhost:9092");
    }

    public String applicationId() {
        return get("kafka.application.id", "KafkaStreamPipe");
    }

    public String autoOffsetReset() {
        return get("kafka.auto.offset.reset", "earliest");
    }

    // ── Topics ───────────────────────────────────────────────────────────────────

    public String inputMetricTopic() {
        return get("topic.metrics.input", "metrics_raw");
    }

    public String inputLogTopic() {
        return get("topic.logs.input", "metrics_raw");
    }

    public String outputMetricTopic() {
        return get("topic.metrics.output", "streams-pipe-output");
    }

    public String outputLogTopic() {
        return get("topic.logs.output", "streams-pipe-output");
    }

    // ── Helpers ──────────────────────────────────────────────────────────────────

    private String get(String key, String defaultValue) {
        return props.getProperty(key, defaultValue);
    }
}

