import yaml


def read_config_file(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path) as f:
        config = yaml.safe_load(f)
        return config
