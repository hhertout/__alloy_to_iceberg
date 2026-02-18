import time
from typing import Any

import numpy as np
import polars as pl
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error

from configs.base import load_limits_settings, load_model_settings
from src.processing.split_df_for_training import split_df_for_training
from utils.logging import get_logger
from utils.queries import get_queries_id


def _to_prophet_frame(df: pl.DataFrame, target_col: str, regressor_cols: list[str], pd: Any) -> Any:
    selected = df.select(["timestamp", target_col, *regressor_cols])
    frame = pd.DataFrame(selected.to_dict(as_series=False))
    frame = frame.rename(columns={"timestamp": "ds", target_col: "y"})
    frame["ds"] = pd.to_datetime(frame["ds"], unit="ms", utc=True).dt.tz_localize(None)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(axis=0)
    frame = frame.copy()
    return frame


def prophet_train_v1(df: pl.DataFrame) -> tuple[object, dict[str, float]]:
    try:
        import pandas as pd

        from prophet import Prophet
    except Exception as exc:
        raise RuntimeError(
            "prophet is unavailable in this environment. Install runtime dependencies first."
        ) from exc

    start = time.time()
    log = get_logger("generate_model")
    limits_settings = load_limits_settings()
    model_settings = load_model_settings()
    training_df, val_df, test_df = split_df_for_training(df)

    target_col = limits_settings.target_column_name
    base_query_cols = list(vars(get_queries_id()).keys())
    regressor_cols = [col for col in base_query_cols if col in df.columns and col != target_col]

    train_pd: Any = _to_prophet_frame(training_df, target_col, regressor_cols, pd)
    eval_df = val_df
    eval_pd: Any = _to_prophet_frame(eval_df, target_col, regressor_cols, pd)

    if len(train_pd) == 0:
        raise ValueError("No valid rows left for Prophet training after dropping NaN/inf values.")
    if len(eval_pd) == 0:
        raise ValueError("No valid rows left for Prophet evaluation after dropping NaN/inf values.")

    prophet_settings = model_settings.prophet
    model = Prophet(
        seasonality_mode=prophet_settings.seasonality_mode,
        changepoint_prior_scale=prophet_settings.changepoint_prior_scale,
        seasonality_prior_scale=prophet_settings.seasonality_prior_scale,
        yearly_seasonality=prophet_settings.yearly_seasonality,
        weekly_seasonality=prophet_settings.weekly_seasonality,
        daily_seasonality=prophet_settings.daily_seasonality,
    )

    for regressor_col in regressor_cols:
        model.add_regressor(regressor_col)

    log.info(
        f"Training Prophet model with {len(train_pd)} samples and {len(regressor_cols)} regressors..."
    )
    model.fit(train_pd)

    future = eval_pd[["ds", *regressor_cols]].copy()
    forecast = model.predict(future)
    predictions = forecast["yhat"].to_numpy(dtype=np.float64)
    y_true = eval_pd["y"].to_numpy(dtype=np.float64)

    mae = mean_absolute_error(y_true, predictions)
    rmse = np.sqrt(mean_squared_error(y_true, predictions))
    mape = mean_absolute_percentage_error(y_true, predictions)
    training_time = time.time() - start

    metrics = {
        "training_time_seconds": training_time,
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
    }

    return model, metrics
