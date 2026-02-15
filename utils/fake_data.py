from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

from configs.constants import TRAINING_TIMEWINDOW_DAYS
from utils.queries import get_queries_id


def generate_fake_dataframe(
    days: int = TRAINING_TIMEWINDOW_DAYS,
    step_seconds: int = 60,
    seed: int = 42,
    cache_path: str = "output/fake/df.parquet",
) -> pl.DataFrame:
    cache_file = Path(cache_path)
    if cache_file.exists():
        return pl.read_parquet(cache_file)

    points = max(1, int(days * 24 * 3600 / step_seconds))
    now_ms = int(datetime.now().timestamp() * 1000)
    start_ms = now_ms - points * step_seconds * 1000

    timestamps = np.arange(start_ms, start_ms + points * step_seconds * 1000, step_seconds * 1000)
    t = np.arange(points, dtype=np.float64)

    rows_per_day = max(1, int(24 * 3600 / step_seconds))
    rows_per_week = max(1, int(7 * rows_per_day))

    rng = np.random.default_rng(seed)

    query_ids = list(vars(get_queries_id()).keys())
    data: dict[str, np.ndarray] = {"timestamp": timestamps.astype(np.int64)}

    generated: dict[str, np.ndarray] = {}
    for query_id in query_ids:
        base_bias = float(rng.uniform(1.0, 20.0))
        w_day = float(rng.uniform(0.2, 4.0))
        w_week = float(rng.uniform(0.2, 3.0))
        w_trend = float(rng.uniform(0.0, 2.0))
        phase_day = float(rng.uniform(0.0, 2.0 * np.pi))
        phase_week = float(rng.uniform(0.0, 2.0 * np.pi))

        signal = (
            base_bias
            + w_day * np.sin(2.0 * np.pi * t / rows_per_day + phase_day)
            + w_week * np.cos(2.0 * np.pi * t / rows_per_week + phase_week)
            + w_trend * (t / max(1.0, float(points - 1)))
        )

        noise_std = max(0.05, 0.05 * float(np.std(signal)))
        noise = rng.normal(loc=0.0, scale=noise_std, size=points)
        values = np.clip(signal + noise, a_min=0.0, a_max=None)
        generated[query_id] = values.astype(np.float64)

    if "cpu_usage" in generated:
        generated["cpu_usage"] = np.clip(generated["cpu_usage"], 0.0, 100.0)

    if "alloy_queue_length" in generated:
        cpu = generated.get("cpu_usage", np.zeros(points, dtype=np.float64))
        loki = generated.get("loki_request_rate", np.zeros(points, dtype=np.float64))
        queue_noise = rng.normal(0.0, 0.2, size=points)
        generated["alloy_queue_length"] = np.clip(
            0.65 * generated["alloy_queue_length"] + 0.25 * cpu + 0.10 * loki + queue_noise,
            a_min=0.0,
            a_max=None,
        )

    for query_id in query_ids:
        data[query_id] = generated[query_id]

    df = pl.DataFrame(data)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(cache_file)
    return df
