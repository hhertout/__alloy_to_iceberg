import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from configs.constants import DatasourceKind, Time
from src.data.grafana_dto import (
    GrafanaDatasource,
    GrafanaQuery,
    GrafanaQueryRequest,
    GrafanaQueryResponse,
)

DEFAULT_TIME_WINDOW = Time.DAY.value

_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)

class GrafanaDao:
    def __init__(self) -> None:
        self.url = os.getenv("GRAFANA_URL")
        self.api_key = os.getenv("GRAFANA_SA_TOKEN")
        self.client = requests.Session()
        self.client.mount("https://", HTTPAdapter(max_retries=_RETRY_STRATEGY))
        self.client.mount("http://", HTTPAdapter(max_retries=_RETRY_STRATEGY))
        self.client.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def get_datasource_uid(self, datasource_name: str) -> str:
        """Retrieves the UID of a Grafana datasource by its name.

        Args:
            datasource_name: The name of the datasource in Grafana.

        Returns:
            The UID of the datasource.

        Raises:
            ValueError: If the datasource is not found.
            requests.HTTPError: If the API request fails.
        """
        response = self.client.get(f"{self.url}/api/datasources", timeout=10)
        response.raise_for_status()
        datasources = response.json()

        for ds in datasources:
            if ds["name"] == datasource_name:
                return ds["uid"]
        raise ValueError(f"Datasource '{datasource_name}' not found in Grafana.")

    def query(
        self,
        kind: DatasourceKind,
        datasource_uid: str,
        expr: str,
        from_time: float | None = None,
        to_time: float | None = None,
    ) -> GrafanaQueryResponse:
        """Executes a query against Grafana's unified query API.

        Args:
            kind: The type of datasource (prometheus, loki, tempo).
            datasource_uid: The UID of the datasource in Grafana.
            expr: The query expression (PromQL, LogQL, or TraceQL).
            from_time: Start time as Unix timestamp (seconds). Defaults to now - 1 hour.
            to_time: End time as Unix timestamp (seconds). Defaults to now.

        Returns:
            GrafanaQueryResponse containing the query results.

        Raises:
            ValueError: If an unsupported datasource kind is provided.
            requests.HTTPError: If the API request fails.
        """
        if to_time is None:
            to_time = time.time()
        if from_time is None:
            from_time = to_time - DEFAULT_TIME_WINDOW

        if not isinstance(kind, DatasourceKind):
            raise ValueError(f"Unsupported kind: {kind}. Use DatasourceKind enum.")

        datasource = GrafanaDatasource(uid=datasource_uid, type=kind.value)
        query = GrafanaQuery(
            ref_id="A",
            datasource=datasource,
            expr=expr,
        )
        request = GrafanaQueryRequest(
            queries=[query],
            from_time=str(int(from_time * 1000)),
            to_time=str(int(to_time * 1000)),
        )

        response = self.client.post(
            f"{self.url}/api/ds/query",
            json=request.to_dict(),
            timeout=30,
        )
        response.raise_for_status()

        return GrafanaQueryResponse.from_dict(response.json())
