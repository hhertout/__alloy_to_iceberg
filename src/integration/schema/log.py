from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform
from pyiceberg.types import (
    ListType,
    NestedField,
    StringType,
    StructType,
    TimestamptzType,
)

LOG_SCHEMA = Schema(
    NestedField(1, "timestamp", TimestamptzType(), required=False),
    NestedField(3, "line", StringType(), required=False),
    NestedField(4, "service_name", StringType(), required=False),
    NestedField(5, "service_namespace", StringType(), required=False),
    NestedField(6, "k8s_namespace_name", StringType(), required=False),
    NestedField(7, "cluster_name", StringType(), required=False),
    NestedField(8, "host", StringType(), required=False),
    NestedField(9, "env", StringType(), required=False),
    NestedField(
        10,
        "resource_attributes",
        ListType(
            element_id=11,
            element_type=StructType(
                NestedField(12, "key", StringType(), required=False),
                NestedField(13, "value", StringType(), required=False),
            ),
            element_required=False,
        ),
        required=False,
    ),
    NestedField(
        14,
        "attributes",
        ListType(
            element_id=15,
            element_type=StructType(
                NestedField(16, "key", StringType(), required=False),
                NestedField(17, "value", StringType(), required=False),
            ),
            element_required=False,
        ),
        required=False,
    ),
)

# Partition by day on timestamp to enable efficient time-range scans and Iceberg snapshot management.
LOG_PARTITION_SPEC = PartitionSpec(
    PartitionField(source_id=1, field_id=1000, transform=DayTransform(), name="timestamp_day")
)
