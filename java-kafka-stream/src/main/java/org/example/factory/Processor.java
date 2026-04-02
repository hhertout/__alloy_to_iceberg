package org.example.factory;

import java.util.List;

public interface Processor<T, G> {
    List<G> process(T data);
}