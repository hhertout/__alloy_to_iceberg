package org.example.serializer;

import com.google.protobuf.InvalidProtocolBufferException;
import com.google.protobuf.Message;
import com.google.protobuf.util.JsonFormat;
import org.apache.kafka.common.errors.SerializationException;
import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serializer;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.function.Supplier;

public class InputSerializer<T extends Message> implements Serializer<T>, Deserializer<T>, Serde<T> {

    private final Supplier<Message.Builder> builderSupplier;

    public InputSerializer(Supplier<Message.Builder> builderSupplier) {
        this.builderSupplier = builderSupplier;
    }

    @Override
    public void configure(final Map<String, ?> configs, final boolean isKey) {
    }

    @Override
    @SuppressWarnings("unchecked")
    public T deserialize(final String topic, final byte[] data) {
        if (data == null) {
            return null;
        }
        try {
            Message.Builder builder = builderSupplier.get();
            JsonFormat.parser()
                    .ignoringUnknownFields()
                    .merge(new String(data, StandardCharsets.UTF_8), builder);
            return (T) builder.build();
        } catch (InvalidProtocolBufferException e) {
            throw new SerializationException("Failed to deserialize protobuf JSON message on topic: " + topic, e);
        }
    }

    @Override
    public byte[] serialize(final String topic, final T data) {
        if (data == null) {
            return null;
        }
        try {
            return JsonFormat.printer().print(data).getBytes(StandardCharsets.UTF_8);
        } catch (InvalidProtocolBufferException e) {
            throw new SerializationException("Failed to serialize protobuf message on topic: " + topic, e);
        }
    }

    @Override
    public void close() {
    }

    @Override
    public Serializer<T> serializer() {
        return this;
    }

    @Override
    public Deserializer<T> deserializer() {
        return this;
    }
}
