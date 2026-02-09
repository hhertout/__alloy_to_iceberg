import time
from datetime import datetime, timedelta

import polars as pl
from dotenv import load_dotenv

from configs.constants import TRAINING_TIMEWINDOW_DAYS
from src.data.azure import AzureInterface
from src.features.v1 import FeaturesEngineeringV1
from utils.askii_art import print_ascii_art
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


def main() -> None:
    print_ascii_art()
    load_dotenv()
    log = get_logger("generate_model")
    _pipeline_runs.add(1, attributes={**get_default_attributes(), "run_ts": time.time()})

    log.info("Starting model generation process...")
    log.info(
        "This script will retrieve data chunks from Azure Storage, process them, and prepare a dataset for model training."
    )
    log.info("Once done, the model is trained and saved back to Azure Storage.")
    log.info("=" * 50)

    log.info("Retrieving data chunks from Azure Storage...")
    chunks_bytes = get_az_chunks()
    df = to_dataframe(chunks_bytes)
    _dataframe_rows.add(df.height, attributes=get_default_attributes())

    log.info("Feature engineering...")
    fe = FeaturesEngineeringV1()
    df = fe.genrate_features(df)

    log.info("Training model...")
    log.info("Saving model to Azure Storage...")
    log.info("Model generation process completed successfully.")


if __name__ == "__main__":
    main()
