package org.example.dtos;

import java.util.List;
import java.util.Optional;

public record OutputLogs(
        String timestamp,
        String line,
        Optional<String> serviceName,
        Optional<String> app,
        Optional<String> env,
        Optional<String> zone,
        Optional<String> k8sNamespaceName,
        Optional<String> clusterName,
        Optional<String> k8sPodName,
        Optional<String> host,
        Optional<String> topic,
        List<KeyValueStore> attributes,
        List<KeyValueStore> resourceAttributes
) {
}
