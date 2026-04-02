package org.example.utils;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.datatype.jdk8.Jdk8Module;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Optional;

public class IngestionConfig {
    public record Config(
            @JsonProperty("rules") ArrayList<AppIngestionConfig> rules) {
    }

    public record AppIngestionConfig(
            @JsonProperty("service.namespace") String serviceNamespace,
            @JsonProperty("service.name") Optional<String> serviceName) {
    }

    public static final ObjectMapper MAPPER = new ObjectMapper(new YAMLFactory())
            .registerModule(new Jdk8Module());

    public static Config loadConfig(String path) {
        try (InputStream stream = Files.newInputStream(Path.of(path))) {
            return MAPPER.readValue(stream, Config.class);
        } catch (Exception e) {
            throw new RuntimeException("Failed to load config file: " + path, e);
        }
    }
}
