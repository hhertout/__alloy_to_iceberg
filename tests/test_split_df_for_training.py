from types import SimpleNamespace

import polars as pl

from src.processing.split_df_for_training import split_df_for_training


class TestSplitDfForTraining:
    def test_split_sizes_with_default_ratios(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.processing.split_df_for_training.load_limits_settings",
            lambda: SimpleNamespace(training_test_size=0.15, training_val_size=0.15),
        )

        df = pl.DataFrame({"x": list(range(100))})
        train_df, val_df, test_df = split_df_for_training(df)

        assert len(train_df) == 70
        assert len(val_df) == 15
        assert len(test_df) == 15

    def test_split_preserves_order(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.processing.split_df_for_training.load_limits_settings",
            lambda: SimpleNamespace(training_test_size=0.2, training_val_size=0.1),
        )

        df = pl.DataFrame({"x": list(range(10))})
        train_df, val_df, test_df = split_df_for_training(df)

        assert train_df["x"].to_list() == [0, 1, 2, 3, 4, 5, 6]
        assert val_df["x"].to_list() == [7]
        assert test_df["x"].to_list() == [8, 9]

    def test_empty_dataframe(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.processing.split_df_for_training.load_limits_settings",
            lambda: SimpleNamespace(training_test_size=0.2, training_val_size=0.1),
        )

        df = pl.DataFrame({"x": []})
        train_df, val_df, test_df = split_df_for_training(df)

        assert len(train_df) == 0
        assert len(val_df) == 0
        assert len(test_df) == 0
