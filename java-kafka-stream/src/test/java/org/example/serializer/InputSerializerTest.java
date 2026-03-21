package org.example.serializer;

import io.opentelemetry.proto.collector.metrics.v1.ExportMetricsServiceRequest;
import io.opentelemetry.proto.metrics.v1.ResourceMetrics;
import org.apache.kafka.common.errors.SerializationException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("InputSerializer / OtlpMetricsSerde")
class InputSerializerTest {

    private static final String TOPIC = "test-topic";

    /** Uses the zero-arg convenience serde – no builder supplier needed. */
    private OtlpMetricsSerde serializer;

    @BeforeEach
    void setUp() {
        serializer = new OtlpMetricsSerde();
    }

    // ------------------------------------------------------------------ null safety

    @Nested
    @DisplayName("null safety")
    class NullSafety {

        @Test
        @DisplayName("deserialize(null bytes) returns null")
        void deserializeNullBytesReturnsNull() {
            assertNull(serializer.deserialize(TOPIC, null));
        }

        @Test
        @DisplayName("serialize(null message) returns null")
        void serializeNullReturnsNull() {
            assertNull(serializer.serialize(TOPIC, null));
        }
    }

    // ------------------------------------------------------------------ serialize

    @Nested
    @DisplayName("serialize")
    class Serialize {

        @Test
        @DisplayName("produces UTF-8 JSON bytes")
        void producesJsonBytes() {
            ExportMetricsServiceRequest request = ExportMetricsServiceRequest.newBuilder()
                    .addResourceMetrics(ResourceMetrics.newBuilder().build())
                    .build();

            byte[] bytes = serializer.serialize(TOPIC, request);

            assertNotNull(bytes);
            String json = new String(bytes, StandardCharsets.UTF_8);
            assertTrue(json.contains("resourceMetrics"), "Serialized JSON should contain 'resourceMetrics' key");
        }

        @Test
        @DisplayName("empty message serializes without error")
        void emptyMessageSerializesWithoutError() {
            ExportMetricsServiceRequest empty = ExportMetricsServiceRequest.getDefaultInstance();
            byte[] bytes = serializer.serialize(TOPIC, empty);
            assertNotNull(bytes);
        }
    }

    // ------------------------------------------------------------------ deserialize

    @Nested
    @DisplayName("deserialize")
    class Deserialize {

        @Test
        @DisplayName("parses minimal valid JSON")
        void parsesMinimalJson() {
            byte[] json = "{}".getBytes(StandardCharsets.UTF_8);
            ExportMetricsServiceRequest result = serializer.deserialize(TOPIC, json);
            assertNotNull(result);
            assertEquals(0, result.getResourceMetricsCount());
        }

        @Test
        @DisplayName("throws SerializationException on invalid JSON")
        void throwsOnInvalidJson() {
            byte[] garbage = "not-json-at-all".getBytes(StandardCharsets.UTF_8);
            assertThrows(SerializationException.class,
                    () -> serializer.deserialize(TOPIC, garbage));
        }
    }

    // ------------------------------------------------------------------ roundtrip

    @Nested
    @DisplayName("roundtrip")
    class Roundtrip {

        @Test
        @DisplayName("serialize then deserialize produces equal message")
        void serializeDeserializeIsIdentical() {
            ExportMetricsServiceRequest original = ExportMetricsServiceRequest.newBuilder()
                    .addResourceMetrics(ResourceMetrics.newBuilder().build())
                    .build();

            byte[] bytes = serializer.serialize(TOPIC, original);
            ExportMetricsServiceRequest restored = serializer.deserialize(TOPIC, bytes);

            assertEquals(original, restored);
        }
    }

    // ------------------------------------------------------------------ fixtures

    @Nested
    @DisplayName("messages.json fixture")
    class FixtureFile {

        private byte[] fixtureBytes() throws IOException, URISyntaxException {
            // Loaded from src/test/fixtures (declared as Maven test resource)
            var url = Thread.currentThread()
                            .getContextClassLoader()
                            .getResource("messages.json");
            assertNotNull(url, "messages.json fixture not found on test classpath");
            return Files.readAllBytes(Path.of(url.toURI()));
        }

        @Test
        @DisplayName("deserializes without error")
        void deserializesWithoutError() throws Exception {
            ExportMetricsServiceRequest request = serializer.deserialize(TOPIC, fixtureBytes());
            assertNotNull(request);
        }

        @Test
        @DisplayName("contains at least one ResourceMetrics entry")
        void containsResourceMetrics() throws Exception {
            ExportMetricsServiceRequest request = serializer.deserialize(TOPIC, fixtureBytes());
            assertFalse(request.getResourceMetricsList().isEmpty(),
                    "messages.json should contain at least one resourceMetrics entry");
        }

        @Test
        @DisplayName("survives a serialize → deserialize roundtrip")
        void roundtripPreservesResourceMetricsCount() throws Exception {
            ExportMetricsServiceRequest original = serializer.deserialize(TOPIC, fixtureBytes());

            byte[] reserialised = serializer.serialize(TOPIC, original);
            ExportMetricsServiceRequest restored = serializer.deserialize(TOPIC, reserialised);

            assertEquals(original.getResourceMetricsCount(), restored.getResourceMetricsCount(),
                    "ResourceMetrics count must survive a serialize/deserialize roundtrip");
        }

        @Test
        @DisplayName("each ResourceMetrics entry preserves its ScopeMetrics count")
        void roundtripPreservesScopeMetricsCount() throws Exception {
            ExportMetricsServiceRequest original = serializer.deserialize(TOPIC, fixtureBytes());
            byte[] reserialised = serializer.serialize(TOPIC, original);
            ExportMetricsServiceRequest restored = serializer.deserialize(TOPIC, reserialised);

            for (int i = 0; i < original.getResourceMetricsCount(); i++) {
                assertEquals(
                        original.getResourceMetrics(i).getScopeMetricsCount(),
                        restored.getResourceMetrics(i).getScopeMetricsCount(),
                        "ScopeMetrics count mismatch at index " + i);
            }
        }
    }

    // ------------------------------------------------------------------ Serde interface

    @Nested
    @DisplayName("Serde interface")
    class SerdeInterface {

        @Test
        @DisplayName("serializer() returns this")
        void serializerReturnsThis() {
            assertSame(serializer, serializer.serializer());
        }

        @Test
        @DisplayName("deserializer() returns this")
        void deserializerReturnsThis() {
            assertSame(serializer, serializer.deserializer());
        }
    }
}

