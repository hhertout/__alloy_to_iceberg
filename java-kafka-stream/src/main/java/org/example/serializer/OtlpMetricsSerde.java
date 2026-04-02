package org.example.serializer;

import io.opentelemetry.proto.collector.metrics.v1.ExportMetricsServiceRequest;

/**
 * Ready-to-use Serde for OTLP {@link ExportMetricsServiceRequest}.
 * <p>
 * Automatically deserializes raw JSON bytes into an
 * {@link ExportMetricsServiceRequest}
 * and serializes it back to JSON bytes – no builder supplier needed.
 *
 * <pre>{@code
 * Consumed.with(Serdes.String(), new OtlpMetricsSerde())
 * }</pre>
 */
public class OtlpMetricsSerde extends InputSerializer<ExportMetricsServiceRequest> {
    public OtlpMetricsSerde() {
        super(ExportMetricsServiceRequest::newBuilder);
    }
}
