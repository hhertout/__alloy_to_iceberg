import polars as pl

from configs.base import load_limits_settings


def split_df_for_training(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Split a DataFrame into train, validation, and test partitions.

    Splits are chronological (no shuffle):
    - train: ``[0:val_start]``
    - validation: ``[val_start:test_start]``
    - test: ``[test_start:]``
    """
    limits_settings = load_limits_settings()

    total = len(df)
    test_start = int(total * (1 - limits_settings.training_test_size))
    val_start = int(
        total * (1 - limits_settings.training_test_size - limits_settings.training_val_size)
    )

    return df[:val_start], df[val_start:test_start], df[test_start:]
