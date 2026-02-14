import time
from typing import IO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from configs.base import load_s3_settings
from configs.constants import (
    DEFAULT_S3_FILE_EXTENSION,
    DEFAULT_S3_FILE_IDENTIFIER,
    DEFAULT_S3_FILE_PREFIX,
)
from utils.exceptions import S3ConnectionError, S3UploadError


class S3Interface:
    def __init__(self) -> None:
        self.__parse_config()
        self.__connect()

    def __parse_config(self) -> None:
        settings = load_s3_settings()
        if not settings.bucket_name:
            raise ValueError("AWS_S3_BUCKET_NAME is required")

        self.bucket_name = settings.bucket_name
        self.region_name = settings.region_name
        self.endpoint_url = settings.endpoint_url
        self.aws_access_key_id = settings.aws_access_key_id
        self.aws_secret_access_key = settings.aws_secret_access_key
        self.aws_session_token = settings.aws_session_token

        self.file_prefix = settings.file_prefix or DEFAULT_S3_FILE_PREFIX
        self.file_identifier = settings.file_identifier or DEFAULT_S3_FILE_IDENTIFIER
        self.file_extension = settings.file_extension or DEFAULT_S3_FILE_EXTENSION

        self.chunk_folder = settings.chunk_folder
        self.models_folder = settings.models_folder

    def __connect(self) -> None:
        try:
            client_kwargs: dict[str, str] = {}
            if self.region_name:
                client_kwargs["region_name"] = self.region_name
            if self.endpoint_url:
                client_kwargs["endpoint_url"] = self.endpoint_url
            if self.aws_access_key_id:
                client_kwargs["aws_access_key_id"] = self.aws_access_key_id
            if self.aws_secret_access_key:
                client_kwargs["aws_secret_access_key"] = self.aws_secret_access_key
            if self.aws_session_token:
                client_kwargs["aws_session_token"] = self.aws_session_token

            self.client = boto3.client("s3", **client_kwargs)
        except (BotoCoreError, ClientError) as error:
            raise S3ConnectionError(f"Failed to connect to S3: {error}") from error

    def __generate_filename(self, date: str) -> str:
        try:
            time.strptime(date, "%Y%m%d")
        except ValueError as error:
            raise ValueError(f"Invalid date format: {date}. Expected YYYYMMDD.") from error
        return f"{self.file_prefix}_{self.file_identifier}_{date}.{self.file_extension}"

    def get_chunk(self, date: str) -> bytes:
        try:
            key = f"{self.chunk_folder}/{self.__generate_filename(date)}"
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            data = response["Body"].read()
            return data
        except (BotoCoreError, ClientError) as error:
            raise S3ConnectionError(f"Failed to retrieve object '{key}': {error}") from error
        except ValueError as error:
            raise ValueError(f"Invalid date provided: {date}. Error: {error}") from error

    def upload_chunk(self, data: bytes | str | IO[bytes]) -> None:
        nowstr = time.strftime("%Y%m%d")
        try:
            key = f"{self.chunk_folder}/{self.__generate_filename(nowstr)}"
            if isinstance(data, str):
                payload: bytes | IO[bytes] = data.encode("utf-8")
            else:
                payload = data

            self.client.put_object(Bucket=self.bucket_name, Key=key, Body=payload)
        except (BotoCoreError, ClientError) as error:
            raise S3UploadError(f"Failed to upload object '{key}': {error}") from error
        except ValueError as error:
            raise ValueError(
                f"Invalid date for filename generation: {nowstr}. Error: {error}"
            ) from error
