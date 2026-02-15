import time

import numpy as np
import polars as pl
from numpy.typing import NDArray
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

from configs.base import load_limits_settings, load_model_settings
from src.processing.normalization import apply_standardization, standardize_train_eval
from src.processing.split_df_for_training import split_df_for_training
from utils.logging import get_logger


def __prepare_for_training(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    training_df, val_df, test_df = split_df_for_training(df)
    return training_df, val_df, test_df


def __rand_forest_train(
    X_train: NDArray[np.float64],
    y_train: NDArray[np.float64],
    X_test: NDArray[np.float64],
    y_test: NDArray[np.float64],
) -> tuple[RandomForestRegressor, dict[str, float]]:
    start = time.time()
    model_settings = load_model_settings()
    model = RandomForestRegressor(
        n_estimators=model_settings.random_forest.n_estimators,
        max_depth=model_settings.random_forest.max_depth,
        min_samples_split=model_settings.random_forest.min_samples_split,
        random_state=model_settings.random_forest.random_state,
        n_jobs=model_settings.random_forest.n_jobs,
        verbose=model_settings.random_forest.verbose,
    )

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    mae = mean_absolute_error(y_test, predictions)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    training_time = time.time() - start
    metrics = {
        "features_number": X_train.shape[1],
        "training_time_seconds": training_time,
        "mae": mae,
        "rmse": rmse,
    }

    return model, metrics


def sklearn_train_rand_forest(df: pl.DataFrame) -> tuple[RandomForestRegressor, dict[str, float]]:
    log = get_logger("generate_model")
    limits_settings = load_limits_settings()
    training_df, val_df, test_df = __prepare_for_training(df)

    feature_cols = [col for col in df.columns if col != limits_settings.target_column_name]
    X_train = training_df.select(feature_cols).to_numpy()
    y_train = training_df.select(limits_settings.target_column_name).to_numpy().ravel()

    eval_df = val_df
    X_test = eval_df.select(feature_cols).to_numpy()
    y_test = eval_df.select(limits_settings.target_column_name).to_numpy().ravel()

    # X_train, X_test, _ = standardize_train_eval(X_train, X_test)

    log.info(
        f"Training Random Forest model with {X_train.shape[0]} samples and {X_train.shape[1]} features..."
    )
    return __rand_forest_train(X_train, y_train, X_test, y_test)


def sklearn_train_xgboost(df: pl.DataFrame) -> tuple[object, dict[str, float]]:
    start = time.time()
    log = get_logger("generate_model")
    limits_settings = load_limits_settings()
    model_settings = load_model_settings()
    training_df, eval_df, test_df = __prepare_for_training(df)

    feature_cols = [col for col in df.columns if col != limits_settings.target_column_name]
    X_train = training_df.select(feature_cols).to_numpy()
    y_train = training_df.select(limits_settings.target_column_name).to_numpy().ravel()

    X_eval = eval_df.select(feature_cols).to_numpy()
    y_eval = eval_df.select(limits_settings.target_column_name).to_numpy().ravel()

    X_test = test_df.select(feature_cols).to_numpy()
    y_test = test_df.select(limits_settings.target_column_name).to_numpy().ravel()

    # X_train, X_eval, scaling_stats = standardize_train_eval(X_train, X_eval)
    # X_test = apply_standardization(X_test, scaling_stats)

    xgb = model_settings.xgboost
    model = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=xgb.n_estimators,
        max_depth=xgb.max_depth,
        learning_rate=xgb.learning_rate,
        subsample=xgb.subsample,
        colsample_bytree=xgb.colsample_bytree,
        random_state=xgb.random_state,
        n_jobs=xgb.n_jobs,
        verbosity=xgb.verbosity,
        min_child_weight=xgb.min_child_weight,
        gamma=xgb.gamma,
        reg_alpha=xgb.reg_alpha,
        reg_lambda=xgb.reg_lambda,
        early_stopping_rounds=50,
    )

    log.info(
        f"Training XGBoost model with {X_train.shape[0]} samples and {X_train.shape[1]} features..."
    )
    model.fit(X_train, y_train, eval_set=[(X_eval, y_eval)])
    predictions = model.predict(X_test)

    mae = mean_absolute_error(y_test, predictions)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    training_time = time.time() - start
    metrics = {
        "features_number": X_train.shape[1],
        "training_time_seconds": training_time,
        "mae": mae,
        "rmse": rmse,
    }

    return model, metrics
