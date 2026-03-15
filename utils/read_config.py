from typing import Any

import yaml


def read_config_file(config_path: str = "configs/config.yaml") -> dict[str, Any]:
    with open(config_path) as f:
        config: dict[str, Any] = yaml.safe_load(f)
        return config
