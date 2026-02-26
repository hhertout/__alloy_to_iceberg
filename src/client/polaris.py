from configs.base import load_integration_settings


class PolarisClient:
    def __init__(self) -> None:
        self.settings = load_integration_settings()
        if self.settings.iceberg.polaris is None:
            raise ValueError("Polaris settings are not configured")
        self.polaris_url = self.settings.iceberg.polaris.url
        self.polaris_token = self.settings.iceberg.polaris.token
