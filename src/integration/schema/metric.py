from pyiceberg.schema import Schema
from pyiceberg.types import (
    DoubleType,
    ListType,
    NestedField,
    StringType,
    StructType,
    TimestamptzType,
)

METRICS_SCHEMA = Schema(
    NestedField(1, "timestamp", TimestamptzType(), required=False),
    NestedField(2, "__name__", StringType(), required=False),
    NestedField(3, "value", DoubleType(), required=False),
    NestedField(4, "service_name", StringType(), required=False),
    NestedField(
        5,
        "resource_attributes",
        ListType(
            6,
            StructType(
                NestedField(7, "key", StringType(), required=False),
                NestedField(8, "value", StringType(), required=False),
            ),
            element_required=False,
        ),
        required=False,
    ),
    NestedField(
        9,
        "attributes",
        ListType(
            10,
            StructType(
                NestedField(11, "key", StringType(), required=False),
                NestedField(12, "value", StringType(), required=False),
            ),
            element_required=False,
        ),
        required=False,
    ),
)
