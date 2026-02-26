import argparse
import time
from datetime import datetime, timedelta

import polars as pl
from dotenv import load_dotenv

from configs.base import load_model_settings
from configs.constants import TRAINING_TIMEWINDOW_DAYS
from src.client.azure import AzureInterface
from src.features.v1 import FeaturesEngineeringV1
from src.prophet.v1 import prophet_train_v1
from src.pytorch.v1 import pytorch_train_lstm
from src.sklearn.v1 import sklearn_train_rand_forest, sklearn_train_xgboost
from utils.askii_art import print_ascii_art
from utils.fake_data import generate_fake_dataframe
from utils.logging import get_logger
from utils.telemetry import get_default_attributes, get_meter

_meter = get_meter("ml_obs.pipeline")
_pipeline_runs = _meter.create_counter(
    "ml.pipeline.generate_model.runs",
    description="Number of pipeline runs",
)

_dataframe_rows = _meter.create_gauge(
    "ml.training.dataframe.rows",
    description="Number of rows in the merged DataFrame",
)

_dataframe_features = _meter.create_gauge(
    "ml.training.features.number",
    description="Number of features in the final training DataFrame after feature engineering",
)

_sklearn_time = _meter.create_gauge(
    "ml.training.sklearn.time.seconds",
    description="Time taken for sklearn model training in seconds",
)

_sklearn_mae = _meter.create_gauge(
    "ml.training.sklearn.mae",
    description="Mean Absolute Error of sklearn model",
)

_sklearn_mape = _meter.create_gauge(
    "ml.training.sklearn.mape",
    description="Mean Absolute Percentage Error of sklearn model",
)

_sklearn_rmse = _meter.create_gauge(
    "ml.training.sklearn.rmse",
    description="Root Mean Squared Error of sklearn model",
)

_pytorch_time = _meter.create_gauge(
    "ml.training.pytorch.time.seconds",
    description="Time taken for pytorch model training in seconds",
)

_pytorch_mae = _meter.create_gauge(
    "ml.training.pytorch.mae",
    description="Mean Absolute Error of pytorch model",
)

_pytorch_rmse = _meter.create_gauge(
    "ml.training.pytorch.rmse",
    description="Root Mean Squared Error of pytorch model",
)

_pytorch_mape = _meter.create_gauge(
    "ml.training.pytorch.mape",
    description="Mean Absolute Percentage Error of pytorch model",
)


def get_az_chunks() -> list[bytes]:
    az = AzureInterface()

    data = []
    for i in range(TRAINING_TIMEWINDOW_DAYS):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            chunk_data = az.get_chunk(date)
            data.append(chunk_data)
        except Exception as e:
            print(f"Error retrieving chunk for date {date}: {e}")

    return data


def to_dataframe(chunks_data: list[bytes]) -> pl.DataFrame:
    merged_df = pl.DataFrame()
    for chunk in chunks_data:
        df = pl.read_parquet(chunk)
        merged_df = pl.concat([merged_df, df])

    return merged_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and train model")
    parser.add_argument(
        "--use-fake",
        action="store_true",
        help="Use synthetic representative data instead of Azure chunks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print_ascii_art()
    load_dotenv()
    log = get_logger("generate_model")
    _pipeline_runs.add(1, attributes={**get_default_attributes(), "run_ts": time.time()})

    log.info("Starting model generation process...")
    log.info(
        "This script will retrieve data chunks from Storage, process them, and prepare a dataset for model training."
    )
    log.info("Once done, the model is trained and saved back to Storage.")
    log.info("=" * 50)

    if args.use_fake:
        log.warning("Using fake synthetic data (--use-fake enabled)...")
        df = generate_fake_dataframe(days=90)
    else:
        log.info("Retrieving data chunks from Storage...")
        chunks_bytes = get_az_chunks()
        df = to_dataframe(chunks_bytes)

    _dataframe_rows.set(df.height, attributes=get_default_attributes())

    log.info("Feature engineering...")
    fe = FeaturesEngineeringV1()
    df = fe.generate_features(df)
    _dataframe_features.set(df.width, attributes=get_default_attributes())

    log.info("Training model...")
    models_settings = load_model_settings()

    if models_settings.random_forest.enabled:
        # Random Forest
        log.info("Training Random Forest model...")
        _, rand_forest_metrics = sklearn_train_rand_forest(df)
        log.info(
            f"Random Forest metrics time={rand_forest_metrics['training_time_seconds']}, mae={rand_forest_metrics['mae']}, rmse={rand_forest_metrics['rmse']}"
        )
        rf_attributes = {**get_default_attributes(), "model_type": "random_forest"}
        _sklearn_time.set(rand_forest_metrics["training_time_seconds"], attributes=rf_attributes)
        _sklearn_mae.set(rand_forest_metrics["mae"], attributes=rf_attributes)
        _sklearn_rmse.set(rand_forest_metrics["rmse"], attributes=rf_attributes)
        _sklearn_mape.set(rand_forest_metrics["mape"], attributes=rf_attributes)

    if models_settings.xgboost.enabled:
        # Xgboost
        log.info("Training XGBoost model...")
        _, xgboost_metrics = sklearn_train_xgboost(df)
        log.info(
            f"XGBoost metrics time={xgboost_metrics['training_time_seconds']}, mae={xgboost_metrics['mae']}, rmse={xgboost_metrics['rmse']}"
        )
        xgb_attributes = {**get_default_attributes(), "model_type": "xgboost"}
        _sklearn_time.set(xgboost_metrics["training_time_seconds"], attributes=xgb_attributes)
        _sklearn_mae.set(xgboost_metrics["mae"], attributes=xgb_attributes)
        _sklearn_rmse.set(xgboost_metrics["rmse"], attributes=xgb_attributes)
        _sklearn_mape.set(xgboost_metrics["mape"], attributes=xgb_attributes)

    if models_settings.prophet.enabled:
        log.info("Training Prophet model...")
        _, prophet_metrics = prophet_train_v1(df)
        log.info(
            f"Prophet metrics time={prophet_metrics['training_time_seconds']}, mae={prophet_metrics['mae']}, rmse={prophet_metrics['rmse']}"
        )
        prophet_attributes = {**get_default_attributes(), "model_type": "prophet"}
        _sklearn_time.set(prophet_metrics["training_time_seconds"], attributes=prophet_attributes)
        _sklearn_mae.set(prophet_metrics["mae"], attributes=prophet_attributes)
        _sklearn_rmse.set(prophet_metrics["rmse"], attributes=prophet_attributes)
        _sklearn_mape.set(xgboost_metrics["mape"], attributes=xgb_attributes)

    if models_settings.pytorch.enabled:
        log.info("Training PyTorch LSTM model...")
        _, pytorch_metrics = pytorch_train_lstm(df)
        log.info(
            f"PyTorch LSTM metrics time={pytorch_metrics['training_time_seconds']}, mae={pytorch_metrics['mae']}, rmse={pytorch_metrics['rmse']}"
        )
        pt_attributes = {**get_default_attributes(), "model_type": "pytorch_lstm"}
        _pytorch_time.set(pytorch_metrics["training_time_seconds"], attributes=pt_attributes)
        _pytorch_mae.set(pytorch_metrics["mae"], attributes=pt_attributes)
        _pytorch_rmse.set(pytorch_metrics["rmse"], attributes=pt_attributes)
        _pytorch_mape.set(pytorch_metrics["mape"], attributes=pt_attributes)

    log.info("Saving model to Azure Storage...")
    log.info("Model generation process completed successfully.")


if __name__ == "__main__":
    main()
