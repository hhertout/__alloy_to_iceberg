package org.example.factory;

import io.opentelemetry.proto.collector.metrics.v1.ExportMetricsServiceRequest;
import io.opentelemetry.proto.common.v1.KeyValue;
import io.opentelemetry.proto.metrics.v1.ExponentialHistogramDataPoint;
import io.opentelemetry.proto.metrics.v1.HistogramDataPoint;
import io.opentelemetry.proto.metrics.v1.Metric;
import io.opentelemetry.proto.metrics.v1.NumberDataPoint;
import io.opentelemetry.proto.metrics.v1.ResourceMetrics;
import io.opentelemetry.proto.metrics.v1.SummaryDataPoint;
import org.example.dtos.KeyValueStore;
import org.example.dtos.OutputMetrics;
import org.example.utils.IngestionConfig;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class MetricProcessor implements Processor<ExportMetricsServiceRequest, OutputMetrics> {
    IngestionConfig.Config ingestionConfig;

    List<String> serviceNamespaceList;
    List<String> serviceNameList;

    public MetricProcessor(IngestionConfig.Config ingestionConfig) {
        this.ingestionConfig = ingestionConfig;

        // All allowed service.namespace values (one per rule)
        this.serviceNamespaceList = this.ingestionConfig
                .rules()
                .stream()
                .map(IngestionConfig.AppIngestionConfig::serviceNamespace)
                .toList();

        // Allowed service.name values — only for rules that define a name filter
        this.serviceNameList = this.ingestionConfig
                .rules()
                .stream()
                .filter(rule -> rule.serviceName().isPresent())
                .map(rule -> rule.serviceName().get())
                .toList();
    }

    @Override
    public List<OutputMetrics> process(ExportMetricsServiceRequest data) {
        System.out.println("Processing data...");
        System.out.println(data);

        List<ResourceMetrics> filtered = data.getResourceMetricsList()
                .stream()
                .filter(resourceMetrics -> matchServiceNamespace(resourceMetrics.getResource().getAttributesList()))
                .toList();

        if (filtered.isEmpty()) {
            return List.of();
        }

        ArrayList<OutputMetrics> response = new ArrayList<>();
        filtered.forEach(resourceMetrics -> {
            List<KeyValueStore> resourceAttr = extractResourceAttributes(resourceMetrics);
            Optional<String> serviceNamespace = extractResourceAttrKey(resourceAttr, "service.namespace");
            if (serviceNamespace.isEmpty()) {
                return;
            }

            resourceMetrics.getScopeMetricsList().forEach(scopeMetrics ->
                    scopeMetrics.getMetricsList().forEach(metric -> {
                        Metric.DataCase type = metric.getDataCase();
                        switch (type) {
                            case GAUGE -> metric.getGauge()
                                    .getDataPointsList()
                                    .forEach(dp -> response.add(processDataPoints(metric, dp, resourceAttr)));
                            case SUM -> metric.getSum()
                                    .getDataPointsList()
                                    .forEach(dp -> response.add(processDataPoints(metric, dp, resourceAttr)));
                            case SUMMARY -> metric.getSummary()
                                    .getDataPointsList()
                                    .forEach(dp -> response.add(processSummaryDataPoints(metric, dp, resourceAttr)));
                            case HISTOGRAM -> metric.getHistogram()
                                    .getDataPointsList()
                                    .forEach(dp -> response.add(processHistogramDataPoints(metric, dp, resourceAttr)));
                            case EXPONENTIAL_HISTOGRAM -> metric.getExponentialHistogram()
                                    .getDataPointsList()
                                    .forEach(dp -> response.add(processExponentialHistogramDataPoints(metric, dp, resourceAttr)));
                            default -> {
                                System.out.println("Unsupported metric type: " + type);
                            }
                        }
                    })
            );
        });

        return response;
    }

    private static Optional<String> extractResourceAttrKey(List<KeyValueStore> resourceAttr, String key) {
        return resourceAttr.stream()
                .filter(el -> el.key().equals(key))
                .findFirst()
                .map(KeyValueStore::value);
    }

    private boolean matchServiceNamespace(List<KeyValue> resourceAttr) {
        KeyValue serviceNamespace = resourceAttr
                .stream()
                .filter(el -> el.getKey().equals("service.namespace"))
                .findFirst()
                .orElse(null);
        KeyValue serviceName = resourceAttr
                .stream()
                .filter(el -> el.getKey().equals("service.name"))
                .findFirst()
                .orElse(null);

        if (serviceNamespace == null) {
            return false;
        }

        boolean isServiceNamespaceMatch = this.serviceNamespaceList.contains(serviceNamespace.getValue().getStringValue());
        if (!isServiceNamespaceMatch) {
            // early return if service namespace doesn't match - Service namespace must be defined
            return false;
        }

        boolean isServiceNameMatch = true;
        Optional<IngestionConfig.AppIngestionConfig> rule = this.ingestionConfig.rules()
                .stream()
                .filter(v -> v.serviceNamespace().equals(serviceNamespace.getValue().getStringValue()))
                .findFirst();

        if (rule.isPresent() && rule.get().serviceName().isPresent() && serviceName != null) {
            isServiceNameMatch = rule.get().serviceName().get()
                    .equals(serviceName.getValue().getStringValue());
        }
        return isServiceNameMatch;
    }

    private List<KeyValueStore> extractResourceAttributes(ResourceMetrics resourceMetrics) {
        return resourceMetrics
                .getResource()
                .getAttributesList()
                .stream()
                .map(rAttr -> new KeyValueStore(rAttr.getKey(), rAttr.getValue().getStringValue()))
                .toList();
    }

    private OutputMetrics processDataPoints(Metric metric, NumberDataPoint dp, List<KeyValueStore> resourceAttr) {
        List<KeyValueStore> attr = dp.getAttributesList()
                .stream()
                .map(v -> new KeyValueStore(v.getKey(), v.getValue().getStringValue()))
                .toList();

        NumberDataPoint.ValueCase valueCase = dp.getValueCase();
        switch (valueCase) {
            case AS_DOUBLE -> {
                return buildOutput(dp.getTimeUnixNano(), metric.getName(), dp.getAsDouble(), Optional.empty(), resourceAttr, attr);
            }
            case AS_INT -> {
                return buildOutput(dp.getTimeUnixNano(), metric.getName(), dp.getAsInt(), Optional.empty(), resourceAttr, attr);
            }
            default -> {
                throw new RuntimeException("Unsupported value type: " + valueCase);
            }
        }
    }

    private OutputMetrics processHistogramDataPoints(Metric metric, HistogramDataPoint dp, List<KeyValueStore> resourceAttr) {
        List<KeyValueStore> attr = dp.getAttributesList()
                .stream()
                .map(v -> new KeyValueStore(v.getKey(), v.getValue().getStringValue()))
                .toList();

        // value = sum, count stored separately — consumer can derive average as value/count
        double value = dp.hasSum() ? dp.getSum() : 0.0;
        return buildOutput(dp.getTimeUnixNano(), metric.getName(), value, Optional.of(dp.getCount()), resourceAttr, attr);
    }

    private OutputMetrics processExponentialHistogramDataPoints(Metric metric, ExponentialHistogramDataPoint dp, List<KeyValueStore> resourceAttr) {
        List<KeyValueStore> attr = dp.getAttributesList()
                .stream()
                .map(v -> new KeyValueStore(v.getKey(), v.getValue().getStringValue()))
                .toList();

        double value = dp.hasSum() ? dp.getSum() : 0.0;
        return buildOutput(dp.getTimeUnixNano(), metric.getName(), value, Optional.of(dp.getCount()), resourceAttr, attr);
    }

    private OutputMetrics processSummaryDataPoints(Metric metric, SummaryDataPoint dp, List<KeyValueStore> resourceAttr) {
        List<KeyValueStore> attr = dp.getAttributesList()
                .stream()
                .map(v -> new KeyValueStore(v.getKey(), v.getValue().getStringValue()))
                .toList();

        // Summary: sum and count are plain proto3 scalars, always present
        return buildOutput(dp.getTimeUnixNano(), metric.getName(), dp.getSum(), Optional.of(dp.getCount()), resourceAttr, attr);
    }

    private OutputMetrics buildOutput(long ts, String metricName, double value, Optional<Long> count, List<KeyValueStore> resourceAttributes, List<KeyValueStore> attributes) {
        return new OutputMetrics(
                ts,
                metricName,
                value,
                count,
                extractResourceAttrKey(resourceAttributes, "service.name"),
                extractResourceAttrKey(resourceAttributes, "service.namespace").orElse("NONE"),
                extractResourceAttrKey(resourceAttributes, "app"),
                extractResourceAttrKey(resourceAttributes, "env"),
                extractResourceAttrKey(resourceAttributes, "zone"),
                extractResourceAttrKey(resourceAttributes, "k8s_namespace_name"),
                extractResourceAttrKey(resourceAttributes, "cluster_name"),
                extractResourceAttrKey(resourceAttributes, "k8s_pod_name"),
                extractResourceAttrKey(resourceAttributes, "host"),
                extractResourceAttrKey(resourceAttributes, "topic"),
                resourceAttributes,
                attributes
        );
    }
}
