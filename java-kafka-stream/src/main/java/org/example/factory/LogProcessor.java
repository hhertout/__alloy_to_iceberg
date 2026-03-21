package org.example.factory;

import io.opentelemetry.proto.collector.logs.v1.ExportLogsServiceRequest;
import org.example.dtos.OutputMetrics;
import java.util.List;

public final class LogProcessor implements Processor<ExportLogsServiceRequest, OutputMetrics> {

    @Override
    public List<OutputMetrics> process(ExportLogsServiceRequest data) {
        System.out.println("Processing data...");
        System.out.println(data);

        if (data == null) {
            return List.of();
        }

        return List.of();
    }
}
