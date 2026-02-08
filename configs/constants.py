from enum import Enum


class DatasourceKind(Enum):
    PROMETHEUS = "prometheus"
    LOKI = "loki"
    TEMPO = "tempo"


class Time(Enum):
    HOUR = 3600
    DAY = 3600 * 24
    WEEK = 3600 * 24 * 7
    MONTH = 3600 * 24 * 30


OUTPUT_DIR = "output"
DATA_DIR = "data"

DEFAULT_AGG_INTERVAL_MS = 60_000
