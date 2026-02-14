from types import SimpleNamespace
from typing import Any

import yaml

from configs.constants import CONFIG_LOKI_KEY, CONFIG_PROM_KEY


def get_queries_id() -> SimpleNamespace:
    """
    Get the list of column based on the queries id defined in the config file.
    Help to provide consistency across all the codebase and avoid hardcoding the column names in multiple places.
    """

    config_path = "configs/queries.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    cols = [query["id"] for ds in config.values() for queries in ds.values() for query in queries]
    return SimpleNamespace(**{col: col for col in cols})


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
