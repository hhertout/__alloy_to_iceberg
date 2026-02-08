import os
import time
from typing import IO

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient

from utils.exceptions import AzureConnectionError, AzureUploadError

class AzureInterface:
    def __init__(self) -> None:
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

        if not connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required")
        if not container_name:
            raise ValueError("AZURE_STORAGE_CONTAINER_NAME is required")

        self.connection_string = connection_string
        self.container_name = container_name

        self.file_prefix = "chunk_"
        self.__connect()

    def __connect(self) -> None:
        """Connects to Azure Storage using the connection string."""
        try:
            self.blob_client = BlobServiceClient.from_connection_string(self.connection_string)
        except AzureError as e:
            raise AzureConnectionError(f"Failed to connect to Azure Storage: {e}") from e

    def upload(self, data: bytes | str | IO[bytes]) -> None:
        """Uploads a file to Azure Storage as a blob.

        Raises:
            AzureUploadError: If the upload fails.
        """
        nowstr = time.strftime("%Y%m%d")
        filename = f"{self.file_prefix}obs-dataset_{nowstr}.parquet"
        print("\nUploading to Azure Storage as blob:\n\t" + filename)
        try:
            conn = self.blob_client.get_blob_client(
                container=self.container_name, blob=filename
            )
            conn.upload_blob(data, overwrite=True)
        except AzureError as e:
            raise AzureUploadError(f"Failed to upload blob '{filename}': {e}") from e
