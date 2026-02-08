from dataclasses import dataclass, field
from typing import Any

from utils.exceptions import DataValidationError


@dataclass(frozen=True)
class TimeSeriesData:
    """Validated time-series result from a Grafana query.

    Guarantees:
        - timestamps and values have the same length
        - timestamps are int (epoch ms), values are float
    """

    query_id: str
    timestamps: list[int]
    values: list[float]

    def __post_init__(self) -> None:
        if len(self.timestamps) != len(self.values):
            raise DataValidationError(
                f"Query '{self.query_id}': timestamps ({len(self.timestamps)}) "
                f"and values ({len(self.values)}) have different lengths."
            )

    @property
    def is_empty(self) -> bool:
        return len(self.timestamps) == 0


@dataclass
class GrafanaDatasource:
    """Represents a Grafana datasource reference."""

    uid: str
    type: str

    def to_dict(self) -> dict:
        return {"uid": self.uid, "type": self.type}


@dataclass
class GrafanaQuery:
    """Represents a single query to a Grafana datasource."""

    ref_id: str
    datasource: GrafanaDatasource
    expr: str
    interval_ms: int = 1000
    max_data_points: int = 1000

    def to_dict(self) -> dict:
        return {
            "refId": self.ref_id,
            "datasource": self.datasource.to_dict(),
            "expr": self.expr,
            "intervalMs": self.interval_ms,
            "maxDataPoints": self.max_data_points,
        }


@dataclass
class GrafanaQueryRequest:
    """Request payload for Grafana's /api/ds/query endpoint."""

    queries: list[GrafanaQuery]
    from_time: str  # Epoch ms as string or relative time (e.g., "now-1h")
    to_time: str  # Epoch ms as string or relative time (e.g., "now")

    def to_dict(self) -> dict:
        return {
            "queries": [q.to_dict() for q in self.queries],
            "from": self.from_time,
            "to": self.to_time,
        }


@dataclass
class GrafanaFrameSchema:
    """Schema information for a Grafana data frame."""

    name: str = ""
    fields: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "GrafanaFrameSchema":
        return cls(
            name=data.get("name", ""),
            fields=data.get("fields", []),
        )


@dataclass
class GrafanaFrameData:
    """Data values for a Grafana data frame."""

    values: list[list[Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "GrafanaFrameData":
        return cls(values=data.get("values", []))


@dataclass
class GrafanaFrame:
    """Represents a single data frame in a Grafana query response."""

    schema: GrafanaFrameSchema
    data: GrafanaFrameData

    @classmethod
    def from_dict(cls, data: dict) -> "GrafanaFrame":
        return cls(
            schema=GrafanaFrameSchema.from_dict(data.get("schema", {})),
            data=GrafanaFrameData.from_dict(data.get("data", {})),
        )


@dataclass
class GrafanaQueryResult:
    """Result for a single query (identified by refId)."""

    ref_id: str
    frames: list[GrafanaFrame]

    @classmethod
    def from_dict(cls, ref_id: str, data: dict) -> "GrafanaQueryResult":
        frames_data = data.get("frames", [])
        return cls(
            ref_id=ref_id,
            frames=[GrafanaFrame.from_dict(f) for f in frames_data],
        )


@dataclass
class GrafanaQueryResponse:
    """Response from Grafana's /api/ds/query endpoint."""

    results: dict[str, GrafanaQueryResult]

    @classmethod
    def from_dict(cls, data: dict) -> "GrafanaQueryResponse":
        results_data = data.get("results", {})
        results = {
            ref_id: GrafanaQueryResult.from_dict(ref_id, result)
            for ref_id, result in results_data.items()
        }
        return cls(results=results)

    def get_frames(self, ref_id: str = "A") -> list[GrafanaFrame]:
        """Get frames for a specific query ref_id."""
        if ref_id in self.results:
            return self.results[ref_id].frames
        return []

    def get_values(self, ref_id: str = "A") -> list[list[Any]]:
        """Get raw values from the first frame of a query result.

        .. deprecated:: Use ``to_time_series`` for validated, typed output.
        """
        frames = self.get_frames(ref_id)
        if frames:
            return frames[0].data.values
        return []

    def to_time_series(self, query_id: str, ref_id: str = "A") -> TimeSeriesData:
        """Extract a validated TimeSeriesData from the response.

        Args:
            query_id: Logical identifier for this query (used in error messages).
            ref_id: The Grafana refId to extract (default "A").

        Returns:
            A validated TimeSeriesData instance.

        Raises:
            DataValidationError: If the frame does not contain exactly 2 columns
                (timestamp + value) or if lengths mismatch.
        """
        frames = self.get_frames(ref_id)
        if not frames:
            return TimeSeriesData(query_id=query_id, timestamps=[], values=[])

        raw = frames[0].data.values
        if len(raw) != 2:
            raise DataValidationError(
                f"Query '{query_id}': expected 2 columns (timestamp, value), "
                f"got {len(raw)}. Raw columns: {[type(c).__name__ for c in raw]}"
            )

        timestamps = [int(t) for t in raw[0]]
        values = [float(v) for v in raw[1]]
        return TimeSeriesData(query_id=query_id, timestamps=timestamps, values=values)
