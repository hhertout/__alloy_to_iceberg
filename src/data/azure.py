import time
from typing import IO

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient

from configs.base import load_azure_settings
from configs.constants import (
    DEFAULT_AZ_FILE_EXTENSION,
    DEFAULT_AZ_FILE_IDENTIFIER,
    DEFAULT_AZ_FILE_PREFIX,
)
from utils.exceptions import AzureConnectionError, AzureUploadError


class AzureInterface:
    def __init__(self) -> None:
        # Load configuration
        self.__parse_config()

        # Connect to Azure Storage
        self.__connect()

    def __parse_config(self) -> None:
        """Parses configuration parameters from a dictionary."""
        settings = load_azure_settings()
        if not settings.connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required")
        if not settings.container_name:
            raise ValueError("AZURE_STORAGE_CONTAINER_NAME is required")

        self.connection_string = settings.connection_string
        self.container_name = settings.container_name
        self.file_prefix = settings.file_prefix or DEFAULT_AZ_FILE_PREFIX
        self.file_identifier = settings.file_identifier or DEFAULT_AZ_FILE_IDENTIFIER
        self.file_extension = settings.file_extension or DEFAULT_AZ_FILE_EXTENSION

        self.chunk_folder = settings.chunk_folder
        self.models_folder = settings.models_folder

    def __connect(self) -> None:
        """Connects to Azure Storage using the connection string."""
        try:
            self.blob_client = BlobServiceClient.from_connection_string(self.connection_string)
        except AzureError as e:
            raise AzureConnectionError(f"Failed to connect to Azure Storage: {e}") from e

    def __generate_filename(self, date: str) -> str:
        """Generates a filename based on the given date."""
        # Validate date format (expecting YYYYMMDD) tested
        try:
            time.strptime(date, "%Y%m%d")
        except ValueError as e:
            raise ValueError(f"Invalid date format: {date}. Expected YYYYMMDD.") from e
        return f"{self.file_prefix}_{self.file_identifier}_{date}.{self.file_extension}"

    def get_chunk(self, date: str) -> bytes:
        """Retrieves a chunk of data to upload.

        In a real implementation, this would read from a file or generate data.
        Here we return dummy data for demonstration purposes.
        """
        try:
            filename = f"{self.chunk_folder}/{self.__generate_filename(date)}"
            conn = self.blob_client.get_blob_client(container=self.container_name, blob=filename)
            data = conn.download_blob().readall()
            return data
        except AzureError as e:
            raise AzureConnectionError(f"Failed to retrieve blob '{filename}': {e}") from e
        except ValueError as e:
            raise ValueError(f"Invalid date provided: {date}. Error: {e}") from e

    def upload_chunk(self, data: bytes | str | IO[bytes]) -> None:
        """Uploads a file to Azure Storage as a blob.

        Raises:
            AzureUploadError: If the upload fails.
        """
        nowstr = time.strftime("%Y%m%d")
        try:
            filename = f"{self.chunk_folder}/{self.__generate_filename(nowstr)}"
            conn = self.blob_client.get_blob_client(container=self.container_name, blob=filename)
            conn.upload_blob(data, overwrite=True)
        except AzureError as e:
            raise AzureUploadError(f"Failed to upload blob '{filename}': {e}") from e
        except ValueError as e:
            raise ValueError(f"Invalid date for filename generation: {nowstr}. Error: {e}") from e
