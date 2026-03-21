package org.example.dtos;

import java.util.List;
import java.util.Optional;

public record OutputMetrics(
        long timestamp,
        String __name__,
        double value,
        Optional<Long> count,
        Optional<String> serviceName,
        String serviceNamespace,
        Optional<String> app,
        Optional<String> env,
        Optional<String> zone,
        Optional<String> k8sNamespaceName,
        Optional<String> clusterName,
        Optional<String> k8sPodName,
        Optional<String> host,
        Optional<String> topic,
        List<KeyValueStore> resourceAttributes,
        List<KeyValueStore> attributes
) {
}
