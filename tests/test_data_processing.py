import polars as pl

from src.processing.data_processing import Processor


class TestIsNullPresent:
    def test_no_nulls(self) -> None:
        df = pl.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        assert Processor.is_null_present(df) is False

    def test_with_null_in_int_column(self) -> None:
        df = pl.DataFrame({"a": [1, None, 3], "b": [4.0, 5.0, 6.0]})
        assert Processor.is_null_present(df) is True

    def test_with_null_in_float_column(self) -> None:
        df = pl.DataFrame({"a": [1, 2, 3], "b": [4.0, None, 6.0]})
        assert Processor.is_null_present(df) is True

    def test_all_nulls(self) -> None:
        df = pl.DataFrame({"a": [None, None], "b": [None, None]})
        assert Processor.is_null_present(df) is True

    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame({"a": pl.Series([], dtype=pl.Int64)})
        assert Processor.is_null_present(df) is False

    def test_nan_is_not_null(self) -> None:
        """NaN ≠ null in Polars — should return False."""
        df = pl.DataFrame({"a": [float("nan"), 1.0]})
        assert Processor.is_null_present(df) is False


class TestIsNanPresent:
    def test_no_nans(self) -> None:
        df = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        assert Processor.is_nan_present(df) is False

    def test_with_nan(self) -> None:
        df = pl.DataFrame({"a": [1.0, float("nan")], "b": [3.0, 4.0]})
        assert Processor.is_nan_present(df) is True

    def test_all_nans(self) -> None:
        df = pl.DataFrame({"a": [float("nan"), float("nan")]})
        assert Processor.is_nan_present(df) is True

    def test_null_is_not_nan(self) -> None:
        """Null ≠ NaN — should return False."""
        df = pl.DataFrame({"a": [None, 1.0]})
        assert Processor.is_nan_present(df) is False

    def test_no_float_columns(self) -> None:
        """Integer-only DataFrame has no NaN concept."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        assert Processor.is_nan_present(df) is False

    def test_empty_float_column(self) -> None:
        df = pl.DataFrame({"a": pl.Series([], dtype=pl.Float64)})
        assert Processor.is_nan_present(df) is False

    def test_mixed_columns_nan_in_one(self) -> None:
        """NaN in one float column among several should be detected."""
        df = pl.DataFrame(
            {
                "x": [1.0, 2.0],
                "y": [3.0, float("nan")],
                "z": [5.0, 6.0],
            }
        )
        assert Processor.is_nan_present(df) is True
