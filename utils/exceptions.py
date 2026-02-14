"""Custom exceptions for the application."""


class DlObsError(Exception):
    """Base exception for all application errors."""


class ConfigurationError(DlObsError):
    """Raised when required configuration is missing or invalid."""


class GrafanaError(DlObsError):
    """Base exception for Grafana-related errors."""


class GrafanaConnectionError(GrafanaError):
    """Raised when connection to Grafana fails."""


class GrafanaQueryError(GrafanaError):
    """Raised when a Grafana query fails."""


class AzureError(DlObsError):
    """Base exception for Azure-related errors."""


class AzureConnectionError(AzureError):
    """Raised when connection to Azure fails."""


class AzureUploadError(AzureError):
    """Raised when upload to Azure Blob Storage fails."""


class S3Error(DlObsError):
    """Base exception for S3-related errors."""


class S3ConnectionError(S3Error):
    """Raised when connection to S3 fails."""


class S3UploadError(S3Error):
    """Raised when upload to S3 fails."""


class DataValidationError(DlObsError):
    """Raised when data does not match the expected schema or format."""
