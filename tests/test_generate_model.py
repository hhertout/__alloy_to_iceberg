import io
from types import SimpleNamespace

import polars as pl
import pytest

from scripts.train import to_dataframe
from utils.fake_data import generate_fake_dataframe


def _make_parquet_bytes(df: pl.DataFrame) -> bytes:
    """Serialize a Polars DataFrame to in-memory Parquet bytes."""
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


class TestToDataframe:
    def test_single_chunk(self) -> None:
        chunk = _make_parquet_bytes(pl.DataFrame({"timestamp": [1, 2], "value": [0.1, 0.2]}))
        result = to_dataframe([chunk])

        assert result.shape == (2, 2)
        assert result["timestamp"].to_list() == [1, 2]
        assert result["value"].to_list() == [pytest.approx(0.1), pytest.approx(0.2)]

    def test_multiple_chunks_concatenated(self) -> None:
        c1 = _make_parquet_bytes(pl.DataFrame({"a": [1, 2], "b": [10.0, 20.0]}))
        c2 = _make_parquet_bytes(pl.DataFrame({"a": [3, 4], "b": [30.0, 40.0]}))
        result = to_dataframe([c1, c2])

        assert result.shape == (4, 2)
        assert result["a"].to_list() == [1, 2, 3, 4]
        assert result["b"].to_list() == [
            pytest.approx(10.0),
            pytest.approx(20.0),
            pytest.approx(30.0),
            pytest.approx(40.0),
        ]

    def test_empty_list_returns_empty_dataframe(self) -> None:
        result = to_dataframe([])
        assert result.shape == (0, 0)

    def test_schema_preserved(self) -> None:
        chunk = _make_parquet_bytes(
            pl.DataFrame(
                {"ts": [1000], "val": [3.14]},
                schema={"ts": pl.Int64, "val": pl.Float64},
            )
        )
        result = to_dataframe([chunk])

        assert result.schema["ts"] == pl.Int64
        assert result.schema["val"] == pl.Float64

    def test_three_chunks(self) -> None:
        chunks = [_make_parquet_bytes(pl.DataFrame({"x": [i]})) for i in range(3)]
        result = to_dataframe(chunks)

        assert result.shape == (3, 1)
        assert result["x"].to_list() == [0, 1, 2]


class TestGenerateFakeDataframe:
    def test_dynamic_columns_from_queries(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "utils.fake_data.get_queries_id",
            lambda: SimpleNamespace(metric_a="metric_a", metric_b="metric_b"),
        )

        cache_path = tmp_path / "df.parquet"
        df = generate_fake_dataframe(days=1, step_seconds=60, seed=7, cache_path=str(cache_path))

        assert "timestamp" in df.columns
        assert "metric_a" in df.columns
        assert "metric_b" in df.columns

    def test_non_negative_values_and_sorted_timestamp(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "utils.fake_data.get_queries_id",
            lambda: SimpleNamespace(metric_x="metric_x"),
        )

        cache_path = tmp_path / "df.parquet"
        df = generate_fake_dataframe(days=1, step_seconds=60, seed=11, cache_path=str(cache_path))

        assert df.height == 1440
        assert all(v >= 0.0 for v in df["metric_x"].to_list())
        ts = df["timestamp"].to_list()
        assert ts == sorted(ts)

    def test_loads_cached_dataframe_when_file_exists(self, monkeypatch, tmp_path) -> None:
        cache_path = tmp_path / "df.parquet"

        monkeypatch.setattr(
            "utils.fake_data.get_queries_id",
            lambda: SimpleNamespace(metric_x="metric_x"),
        )
        first_df = generate_fake_dataframe(
            days=1, step_seconds=60, seed=11, cache_path=str(cache_path)
        )

        monkeypatch.setattr(
            "utils.fake_data.get_queries_id",
            lambda: (_ for _ in ()).throw(RuntimeError("should not regenerate")),
        )
        second_df = generate_fake_dataframe(
            days=30, step_seconds=300, seed=99, cache_path=str(cache_path)
        )

        assert first_df.equals(second_df)
