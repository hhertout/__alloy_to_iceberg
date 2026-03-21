package org.example.serializer;

import io.opentelemetry.proto.collector.logs.v1.ExportLogsServiceRequest;

/**
 * Ready-to-use Serde for OTLP {@link ExportLogsServiceRequest}.
 * <p>
 * Automatically deserializes raw JSON bytes into an {@link ExportLogsServiceRequest}
 * and serializes it back to JSON bytes – no builder supplier needed.
 *
 * <pre>{@code
 * Consumed.with(Serdes.String(), new OtlpMetricsSerde())
 * }</pre>
 */
public class OtlpLogsSerde extends InputSerializer<ExportLogsServiceRequest> {
    public OtlpLogsSerde() {
        super(ExportLogsServiceRequest::newBuilder);
    }
}
