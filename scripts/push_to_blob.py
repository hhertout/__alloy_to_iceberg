import argparse
import asyncio
import time
from pathlib import Path
from typing import Any

import polars as pl
import yaml
from dotenv import load_dotenv

from configs.constants import OUTPUT_DIR, DatasourceKind
from src.data.azure import AzureInterface
from src.data.grafana import GrafanaDao
from src.data.grafana_dto import TimeSeriesData
from src.dataviz.quick_preview import visualize_df
from src.processing.data_processing import Processor
from src.processing.merge_dataframes import merge_dataframes
from utils import get_logger, get_meter, shutdown_telemetry
from utils.askii_art import print_ascii_art
from utils.exceptions import DataValidationError
from utils.telemetry import get_default_attributes
from utils.timerange import get_previous_day_range

CONFIG_PROM_KEY = "prometheus"
CONFIG_LOKI_KEY = "loki"

# ── OTel custom metrics ──
_meter = get_meter("ml_obs.pipeline")
_pipeline_runs = _meter.create_counter(
    "ml.pipeline.push_to_blob.runs",
    description="Number of pipeline runs",
)
_queries_total = _meter.create_counter(
    "ml.grafana.queries.total",
    description="Total number of queries executed",
)
_queries_failed = _meter.create_counter(
    "ml.grafana.queries.failed",
    description="Number of failed queries",
)
_query_duration = _meter.create_histogram(
    "ml.grafana.query.duration",
    description="Duration of individual query fetches in seconds",
    unit="s",
)
_dataframe_rows = _meter.create_up_down_counter(
    "ml.dataframe.rows",
    description="Number of rows in the merged DataFrame",
)

_push_to_blob_failed = _meter.create_counter(
    "ml.blob.push.failed",
    description="Number of failed push to blob operations",
)


def read_queries_file(config_path: str = "configs/queries.yaml") -> Any:
    with open(config_path) as f:
        queries = yaml.safe_load(f)
        return queries


def extract_promtheus_queries(queries: Any) -> dict[str, list[dict[str, str]]]:
    """Extracts Prometheus queries from the configuration."""
    result: dict[str, list[dict[str, str]]] = queries.get(CONFIG_PROM_KEY, {})
    return result


def extract_loki_queries(queries: Any) -> dict[str, list[dict[str, str]]]:
    """Extracts Loki queries from the configuration."""
    result: dict[str, list[dict[str, str]]] = queries.get(CONFIG_LOKI_KEY, {})
    return result


async def _fetch_query(
    grafana_dao: GrafanaDao,
    kind: DatasourceKind,
    datasource_uid: str,
    query: dict[str, str],
    from_time: float,
    to_time: float,
) -> TimeSeriesData | None:
    """Executes a single Grafana query and returns validated TimeSeriesData."""
    log = get_logger("push_to_blob")
    query_id = query["id"]
    _queries_total.add(1, attributes=get_default_attributes())
    start = time.monotonic()
    try:
        response = await asyncio.to_thread(
            grafana_dao.query,
            kind=kind,
            datasource_uid=datasource_uid,
            expr=query["query"],
            from_time=from_time,
            to_time=to_time,
        )
        return response.to_time_series(query_id, agg=query.get("agg", "mean"))
    except DataValidationError as e:
        _queries_failed.add(1, attributes=get_default_attributes())
        log.error(f"Validation failed for query '{query_id}': {e}")
        return None
    except Exception as e:
        _queries_failed.add(1, attributes=get_default_attributes())
        log.error(f"Error executing query '{query_id}': {e}")
        return None
    finally:
        _query_duration.record(time.monotonic() - start, attributes=get_default_attributes())


async def _fetch_for_kind(
    grafana_dao: GrafanaDao,
    kind: DatasourceKind,
    ds_configs: dict[str, list[dict[str, str]]],
    from_time: float,
    to_time: float,
) -> dict[str, TimeSeriesData]:
    """Fetches all queries for a given datasource kind in parallel."""
    log = get_logger("push_to_blob")
    tasks: list[asyncio.Task[TimeSeriesData | None]] = []

    for ds_name, ds_queries in ds_configs.items():
        datasource_uid = await asyncio.to_thread(grafana_dao.get_datasource_uid, ds_name)
        for query in ds_queries:
            tasks.append(
                asyncio.create_task(
                    _fetch_query(grafana_dao, kind, datasource_uid, query, from_time, to_time)
                )
            )

    results: list[TimeSeriesData | None] = await asyncio.gather(*tasks)

    data: dict[str, TimeSeriesData] = {}
    for ts_data in results:
        if ts_data is None:
            continue
        if ts_data.query_id in data:
            log.warning(f"Duplicate query id '{ts_data.query_id}'. Overwriting.")
        data[ts_data.query_id] = ts_data
    return data


async def retrieve_data(
    grafana_dao: GrafanaDao,
    queries: dict[str, Any],
    from_time: float,
    to_time: float,
) -> dict[str, TimeSeriesData]:
    """Retrieves data from Grafana, running Prometheus and Loki queries in parallel."""
    prom_configs = extract_promtheus_queries(queries)
    loki_configs = extract_loki_queries(queries)

    prom_data, loki_data = await asyncio.gather(
        _fetch_for_kind(grafana_dao, DatasourceKind.PROMETHEUS, prom_configs, from_time, to_time),
        _fetch_for_kind(grafana_dao, DatasourceKind.LOKI, loki_configs, from_time, to_time),
    )

    # Merge results (loki overwrites prometheus on duplicate ids)
    return {**prom_data, **loki_data}


def convert_dataframes(data: dict[str, TimeSeriesData]) -> dict[str, pl.DataFrame]:
    """Converts validated TimeSeriesData to Polars DataFrames.

    Filters out rows with NaN values or negative timestamps and logs
    warnings when rows are dropped.
    """
    log = get_logger("push_to_blob")
    result: dict[str, pl.DataFrame] = {}
    for query_id, ts_data in data.items():
        if ts_data.is_empty:
            log.warning(f"Query '{query_id}' returned no data. Skipping.")
            continue
        df = pl.DataFrame(
            {"timestamp": ts_data.timestamps, "value": ts_data.values},
            schema={"timestamp": pl.Int64, "value": pl.Float64},
        )
        initial_len = len(df)
        df = df.filter(pl.col("value").is_not_nan())
        df = df.filter(pl.col("timestamp") > 0)
        dropped = initial_len - len(df)
        if dropped > 0:
            log.warning(
                f"Query '{query_id}': dropped {dropped} row(s) (NaN values or negative timestamps)."
            )
        result[query_id] = df
    return result


def process_data(processor: Processor, df: pl.DataFrame) -> pl.DataFrame:
    """Processes the data using the provided processor."""
    return processor.process(df)


def push_to_blob(file: str) -> None:
    """Pushes data to blob storage."""
    az = AzureInterface()
    with open(file, "rb") as f:
        az.upload_chunk(f)


async def main(force: bool) -> None:
    print_ascii_art()
    load_dotenv()
    log = get_logger("push_to_blob")
    _pipeline_runs.add(1, attributes={**get_default_attributes(), "run_ts": f"{time.time()}"})
    if force:
        log.warning(
            "Force mod is enabled - Ignoring dataviz and pushing data directly to blob storage."
        )

    grafana_dao = GrafanaDao()

    log.info("Executing push_to_blob.py...")
    log.info(
        "This script pushes required data, metrics coming from Grafana, to azure storage for long-term storage..."
    )
    log.info("Metrics queried selected in configs/queries.yaml.")
    log.info(
        "Metrics selected are representative of the behavior of the system and should provide to ML models the necessary information to learn and predict on the system's behavior."
    )
    log.info("=" * 50)

    # Step 1: Retrieve and convert data
    log.info("Parsing queries...")

    queries = read_queries_file()
    if not queries:
        log.error("No queries found in configs/queries.yaml")
        _push_to_blob_failed.add(1, attributes=get_default_attributes())
        exit(1)

    from_time, to_time = get_previous_day_range()

    log.info("Retrieving data from grafana...")
    data = await retrieve_data(grafana_dao, queries, from_time, to_time)
    log.info("Data retrieval complete.")

    # Step 3: Merging dataframes (merged on timestamp) and converting to parquet
    log.info("Merging and resampling dataframes...")

    file = f"{OUTPUT_DIR}/output.parquet"
    merged_df = merge_dataframes(data, metric=_dataframe_rows)

    log.info("Processing dataset...")
    merged_df = Processor.process(merged_df)

    if Processor.is_null_present(merged_df) or Processor.is_nan_present(merged_df):
        _push_to_blob_failed.add(1, attributes=get_default_attributes())
        log.error(
            "Null or NaN values detected in the merged dataframe after processing. Please check the data and processing steps."
        )
        exit(1)

    log.info("Saving merged dataframe to parquet...")
    merged_df = merged_df.sort("timestamp")
    merged_df.write_parquet(file, compression="snappy")

    # Step 4: Push to Azure Blob Storage
    # If not in force mode, visualize the data and ask for confirmation before pushing to blob storage.
    # This is a safety measure to prevent pushing bad data to blob storage and also to provide a quick preview of the data being pushed.
    if not force:
        log.info("Visualizing data before pushing to blob storage...")
        print(merged_df.head())
        visualize_df(merged_df, "Merged DataFrame", merged_df.columns[1:])

        confirm = input("Do you want to push data to blob storage? (y/N): ").strip().lower()
        if confirm != "y" and confirm != "yes" and confirm != "1":
            log.info("Push cancelled by user.")
            return

    log.info("Pushing to Azure blob storage 📦...")
    try:
        push_to_blob(file=file)
    except Exception as e:
        _push_to_blob_failed.add(1, attributes=get_default_attributes())
        Path(file).unlink()
        log.error(f"Failed to push to Azure blob storage: {e}")
        log.error("Exiting...")
        return

    # Step 5: Cleanup local file
    log.info("🎉 Data successfully pushed to Azure blob storage.")
    try:
        Path(file).unlink()
    except Exception as e:
        log.error(f"Failed to delete local file: {e}")
    shutdown_telemetry()


if __name__ == "__main__":
    """
    Run with --force to skip dataviz and push data directly to blob storage.
    Use it whithin CI/CD pipeline.
    """
    parser = argparse.ArgumentParser(description="Push data to Azure Blob Storage.")
    parser.add_argument(
        "--force", action="store_true", help="Force push even if data already exists."
    )
    args = parser.parse_args()

    asyncio.run(main(force=args.force))
