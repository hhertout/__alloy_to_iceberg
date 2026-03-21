package org.example.factory;

import java.util.List;
import java.util.Optional;

public interface Processor<T, G> {
    List<G> process(T data);
}