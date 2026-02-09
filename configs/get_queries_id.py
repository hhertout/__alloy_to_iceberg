from types import SimpleNamespace

import yaml


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


if __name__ == "__main__":
    cols = get_queries_id()
    print(cols)
