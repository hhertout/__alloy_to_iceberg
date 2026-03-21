package org.example.factory;

import io.opentelemetry.proto.collector.metrics.v1.ExportMetricsServiceRequest;
import io.opentelemetry.proto.common.v1.AnyValue;
import io.opentelemetry.proto.common.v1.KeyValue;
import io.opentelemetry.proto.metrics.v1.Gauge;
import io.opentelemetry.proto.metrics.v1.Histogram;
import io.opentelemetry.proto.metrics.v1.HistogramDataPoint;
import io.opentelemetry.proto.metrics.v1.Metric;
import io.opentelemetry.proto.metrics.v1.NumberDataPoint;
import io.opentelemetry.proto.metrics.v1.ResourceMetrics;
import io.opentelemetry.proto.metrics.v1.ScopeMetrics;
import io.opentelemetry.proto.resource.v1.Resource;
import org.example.dtos.OutputMetrics;
import org.example.serializer.OtlpMetricsSerde;
import org.example.utils.IngestionConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("MetricProcessor")
class MetricProcessorTest {

    // ── Constants matching the fixture file ──────────────────────────────────
    private static final String FIXTURE_SERVICE_NAME      = "redpanda";
    private static final String FIXTURE_SERVICE_NAMESPACE = "redpanda";
    private static final int    FIXTURE_TOTAL_DATAPOINTS  = 898;  // 98 metrics × N datapoints
    private static final String FIRST_METRIC_NAME =
            "redpanda_debug_bundle_last_failed_bundle_timestamp_seconds";

    // ── Helpers ──────────────────────────────────────────────────────────────

    /** Config that allows any service under the given namespace (no service.name filter). */
    private static MetricProcessor processorFor(String namespace) {
        IngestionConfig.Config config = new IngestionConfig.Config(new ArrayList<>(List.of(
                new IngestionConfig.AppIngestionConfig(namespace, Optional.empty())
        )));
        return new MetricProcessor(config);
    }

    /** Config with both a namespace AND a service.name filter. */
    private static MetricProcessor processorFor(String namespace, String serviceName) {
        IngestionConfig.Config config = new IngestionConfig.Config(new ArrayList<>(List.of(
                new IngestionConfig.AppIngestionConfig(namespace, Optional.of(serviceName))
        )));
        return new MetricProcessor(config);
    }

    private static KeyValue kv(String key, String value) {
        return KeyValue.newBuilder()
                .setKey(key)
                .setValue(AnyValue.newBuilder().setStringValue(value).build())
                .build();
    }

    private static ExportMetricsServiceRequest buildGaugeRequest(
            String namespace, String serviceName, String metricName, double value, long timeNano) {

        NumberDataPoint dp = NumberDataPoint.newBuilder()
                .setAsDouble(value)
                .setTimeUnixNano(timeNano)
                .addAttributes(kv("env", "prod"))
                .build();

        Metric metric = Metric.newBuilder()
                .setName(metricName)
                .setGauge(Gauge.newBuilder().addDataPoints(dp).build())
                .build();

        return ExportMetricsServiceRequest.newBuilder()
                .addResourceMetrics(ResourceMetrics.newBuilder()
                        .setResource(Resource.newBuilder()
                                .addAttributes(kv("service.namespace", namespace))
                                .addAttributes(kv("service.name", serviceName))
                                .build())
                        .addScopeMetrics(ScopeMetrics.newBuilder()
                                .addMetrics(metric)
                                .build())
                        .build())
                .build();
    }

    /** Loads and deserializes the fixture, then injects the given service.namespace. */
    private static ExportMetricsServiceRequest fixtureWithNamespace(String namespace)
            throws Exception {
        var url = Thread.currentThread().getContextClassLoader().getResource("messages.json");
        assertNotNull(url, "messages.json fixture not found on test classpath");
        byte[] json = Files.readAllBytes(Path.of(url.toURI()));

        ExportMetricsServiceRequest base = new OtlpMetricsSerde().deserialize("test", json);

        // Inject service.namespace into each ResourceMetrics
        List<ResourceMetrics> enriched = base.getResourceMetricsList().stream()
                .map(rm -> rm.toBuilder()
                        .setResource(rm.getResource().toBuilder()
                                .addAttributes(kv("service.namespace", namespace))
                                .build())
                        .build())
                .toList();

        return ExportMetricsServiceRequest.newBuilder()
                .addAllResourceMetrics(enriched)
                .build();
    }

    // ── Filtering ────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("filtering")
    class Filtering {

        @Test
        @DisplayName("returns empty when no service.namespace in request")
        void returnsEmptyWhenNoNamespaceInRequest() {
            MetricProcessor processor = processorFor("redpanda");
            ExportMetricsServiceRequest request = ExportMetricsServiceRequest.newBuilder()
                    .addResourceMetrics(ResourceMetrics.newBuilder()
                            .setResource(Resource.newBuilder()
                                    .addAttributes(kv("service.name", "redpanda"))
                                    .build())
                            .build())
                    .build();

            assertTrue(processor.process(request).isEmpty());
        }

        @Test
        @DisplayName("returns empty when namespace does not match any rule")
        void returnsEmptyWhenNamespaceDoesNotMatch() {
            MetricProcessor processor = processorFor("other-namespace");
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "cpu", 1.0, 1000L));

            assertTrue(result.isEmpty());
        }

        @Test
        @DisplayName("returns elements when namespace matches")
        void returnsElementsWhenNamespaceMatches() {
            MetricProcessor processor = processorFor("redpanda");
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "cpu", 1.0, 1000L));

            assertFalse(result.isEmpty());
        }

        @Test
        @DisplayName("returns elements when namespace matches and no service.name filter in rule")
        void returnsElementsWhenNoServiceNameFilter() {
            MetricProcessor processor = processorFor("redpanda"); // no service.name filter
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "any-service", "cpu", 1.0, 1000L));

            assertFalse(result.isEmpty());
        }

        @Test
        @DisplayName("returns elements when namespace AND service.name both match")
        void returnsElementsWhenBothMatch() {
            MetricProcessor processor = processorFor("redpanda", "redpanda");
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "cpu", 1.0, 1000L));

            assertFalse(result.isEmpty());
        }

        @Test
        @DisplayName("returns empty when namespace matches but service.name does not")
        void returnsEmptyWhenServiceNameDoesNotMatch() {
            MetricProcessor processor = processorFor("redpanda", "allowed-service");
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "other-service", "cpu", 1.0, 1000L));

            assertTrue(result.isEmpty());
        }

        @Test
        @DisplayName("returns empty when request is empty")
        void returnsEmptyForEmptyRequest() {
            MetricProcessor processor = processorFor("redpanda");
            assertTrue(processor.process(ExportMetricsServiceRequest.getDefaultInstance()).isEmpty());
        }
    }

    // ── OutputMetrics field mapping ───────────────────────────────────────────

    @Nested
    @DisplayName("output field mapping")
    class OutputFieldMapping {

        private final MetricProcessor processor = processorFor("redpanda");
        private final long TS = 1_000_000L;

        @Test
        @DisplayName("metric name is mapped to __name__")
        void metricNameIsMapped() {
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "my_metric", 42.0, TS));

            assertEquals("my_metric", result.get(0).__name__());
        }

        @Test
        @DisplayName("timestamp is mapped correctly")
        void timestampIsMapped() {
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "my_metric", 42.0, TS));

            assertEquals(TS, result.get(0).timestamp());
        }

        @Test
        @DisplayName("service.name resource attribute is extracted")
        void serviceNameIsExtracted() {
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "my_metric", 42.0, TS));

            assertEquals(Optional.of("redpanda"), result.get(0).serviceName());
        }

        @Test
        @DisplayName("service.namespace resource attribute is extracted")
        void serviceNamespaceIsExtracted() {
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "my_metric", 42.0, TS));

            assertEquals("redpanda", result.get(0).serviceNamespace());
        }
    }

    // ── Gauge metrics ────────────────────────────────────────────────────────

    @Nested
    @DisplayName("GAUGE metrics")
    class GaugeMetrics {

        private final MetricProcessor processor = processorFor("redpanda");

        @Test
        @DisplayName("produces one OutputMetrics per datapoint")
        void producesOneOutputPerDatapoint() {
            NumberDataPoint dp1 = NumberDataPoint.newBuilder().setAsDouble(1.0).setTimeUnixNano(100L).build();
            NumberDataPoint dp2 = NumberDataPoint.newBuilder().setAsDouble(2.0).setTimeUnixNano(200L).build();
            Metric metric = Metric.newBuilder()
                    .setName("cpu")
                    .setGauge(Gauge.newBuilder().addDataPoints(dp1).addDataPoints(dp2).build())
                    .build();
            ExportMetricsServiceRequest request = ExportMetricsServiceRequest.newBuilder()
                    .addResourceMetrics(ResourceMetrics.newBuilder()
                            .setResource(Resource.newBuilder()
                                    .addAttributes(kv("service.namespace", "redpanda"))
                                    .addAttributes(kv("service.name", "redpanda"))
                                    .build())
                            .addScopeMetrics(ScopeMetrics.newBuilder().addMetrics(metric).build())
                            .build())
                    .build();

            assertEquals(2, processor.process(request).size());
        }

        @Test
        @DisplayName("value is mapped from asDouble")
        void valueFromAsDouble() {
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "cpu", 3.14, 1000L));

            assertEquals(3.14, result.get(0).value());
        }

        @Test
        @DisplayName("count is empty for GAUGE")
        void countIsEmptyForGauge() {
            List<OutputMetrics> result = processor.process(
                    buildGaugeRequest("redpanda", "redpanda", "cpu", 1.0, 1000L));

            assertTrue(result.get(0).count().isEmpty());
        }
    }

    // ── Histogram metrics ────────────────────────────────────────────────────

    @Nested
    @DisplayName("HISTOGRAM metrics")
    class HistogramMetrics {

        private final MetricProcessor processor = processorFor("redpanda");

        private ExportMetricsServiceRequest histogramRequest(double sum, long count) {
            HistogramDataPoint dp = HistogramDataPoint.newBuilder()
                    .setSum(sum)
                    .setCount(count)
                    .setTimeUnixNano(5000L)
                    .build();
            Metric metric = Metric.newBuilder()
                    .setName("latency")
                    .setHistogram(Histogram.newBuilder().addDataPoints(dp).build())
                    .build();
            return ExportMetricsServiceRequest.newBuilder()
                    .addResourceMetrics(ResourceMetrics.newBuilder()
                            .setResource(Resource.newBuilder()
                                    .addAttributes(kv("service.namespace", "redpanda"))
                                    .addAttributes(kv("service.name", "redpanda"))
                                    .build())
                            .addScopeMetrics(ScopeMetrics.newBuilder().addMetrics(metric).build())
                            .build())
                    .build();
        }

        @Test
        @DisplayName("value is set to sum")
        void valueIsSum() {
            List<OutputMetrics> result = processor.process(histogramRequest(250.0, 10));
            assertEquals(250.0, result.get(0).value());
        }

        @Test
        @DisplayName("count is present for HISTOGRAM")
        void countIsPresentForHistogram() {
            List<OutputMetrics> result = processor.process(histogramRequest(250.0, 10));
            assertEquals(Optional.of(10L), result.get(0).count());
        }

        @Test
        @DisplayName("value is 0.0 when sum is absent")
        void valueIsZeroWhenSumAbsent() {
            HistogramDataPoint dp = HistogramDataPoint.newBuilder()
                    .setCount(5)
                    .setTimeUnixNano(1000L)
                    // no setSum() → hasSum() = false
                    .build();
            Metric metric = Metric.newBuilder()
                    .setName("latency")
                    .setHistogram(Histogram.newBuilder().addDataPoints(dp).build())
                    .build();
            ExportMetricsServiceRequest request = ExportMetricsServiceRequest.newBuilder()
                    .addResourceMetrics(ResourceMetrics.newBuilder()
                            .setResource(Resource.newBuilder()
                                    .addAttributes(kv("service.namespace", "redpanda"))
                                    .build())
                            .addScopeMetrics(ScopeMetrics.newBuilder().addMetrics(metric).build())
                            .build())
                    .build();

            assertEquals(0.0, processor.process(request).get(0).value());
        }
    }

    // ── Fixture file ─────────────────────────────────────────────────────────

    @Nested
    @DisplayName("messages.json fixture")
    class FixtureFile {

        @Test
        @DisplayName("returns empty when fixture has no service.namespace (filter rejects it)")
        void returnsEmptyForRawFixture() throws Exception {
            var url = Thread.currentThread().getContextClassLoader().getResource("messages.json");
            assertNotNull(url);
            byte[] json = Files.readAllBytes(Path.of(url.toURI()));
            ExportMetricsServiceRequest request = new OtlpMetricsSerde().deserialize("test", json);

            List<OutputMetrics> result = processorFor(FIXTURE_SERVICE_NAMESPACE).process(request);

            assertTrue(result.isEmpty(),
                    "Raw fixture has no service.namespace — should be filtered out");
        }

        @Test
        @DisplayName("returns one OutputMetrics per datapoint when namespace is injected")
        void returnsOneOutputPerDatapointWithNamespace() throws Exception {
            ExportMetricsServiceRequest request = fixtureWithNamespace(FIXTURE_SERVICE_NAMESPACE);
            List<OutputMetrics> result = processorFor(FIXTURE_SERVICE_NAMESPACE).process(request);

            assertEquals(FIXTURE_TOTAL_DATAPOINTS, result.size());
        }

        @Test
        @DisplayName("all output elements carry the correct service.name")
        void allElementsHaveCorrectServiceName() throws Exception {
            ExportMetricsServiceRequest request = fixtureWithNamespace(FIXTURE_SERVICE_NAMESPACE);
            List<OutputMetrics> result = processorFor(FIXTURE_SERVICE_NAMESPACE).process(request);

            assertTrue(result.stream().allMatch(
                    m -> m.serviceName().equals(Optional.of(FIXTURE_SERVICE_NAME))));
        }

        @Test
        @DisplayName("all output elements carry the correct service.namespace")
        void allElementsHaveCorrectServiceNamespace() throws Exception {
            ExportMetricsServiceRequest request = fixtureWithNamespace(FIXTURE_SERVICE_NAMESPACE);
            List<OutputMetrics> result = processorFor(FIXTURE_SERVICE_NAMESPACE).process(request);

            assertTrue(result.stream().allMatch(
                    m -> m.serviceNamespace().equals(FIXTURE_SERVICE_NAMESPACE)));
        }

        @Test
        @DisplayName("count is empty for all elements (fixture contains only GAUGE metrics)")
        void countIsEmptyForAllGaugeMetrics() throws Exception {
            ExportMetricsServiceRequest request = fixtureWithNamespace(FIXTURE_SERVICE_NAMESPACE);
            List<OutputMetrics> result = processorFor(FIXTURE_SERVICE_NAMESPACE).process(request);

            assertTrue(result.stream().allMatch(m -> m.count().isEmpty()));
        }

        @Test
        @DisplayName("first OutputMetrics matches known fixture values")
        void firstOutputMatchesFixtureValues() throws Exception {
            ExportMetricsServiceRequest request = fixtureWithNamespace(FIXTURE_SERVICE_NAMESPACE);
            List<OutputMetrics> result = processorFor(FIXTURE_SERVICE_NAMESPACE).process(request);

            OutputMetrics first = result.get(0);
            assertEquals(FIRST_METRIC_NAME, first.__name__());
            assertEquals(1772043702670000000L, first.timestamp());
            assertEquals(0.0, first.value());
        }
    }
}

