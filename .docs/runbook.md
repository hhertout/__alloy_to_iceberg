# Runbook

## Blob Storage: overwrite behavior

The Azure Blob Storage upload uses `overwrite=True`. This means that **any blob with the same name is silently replaced** — no versioning, no backup, no warning.

Because the blob naming convention is date-based (`chunks/chunk_dataframe_YYYYMMDD.parquet`), running the pipeline **multiple times on the same day will overwrite the previous chunk** with the latest data. Only the last run of the day is kept.

### What to watch out for

- **Multiple runs per day**: If the script is triggered more than once in a given day (manually or via CI/CD), the earlier run's data is lost. There is no append or deduplication logic — the file is fully replaced.
- **File naming is tied to the current date** (`time.strftime("%Y%m%d")`), not to the data's time range. The data covers the **previous day** (yesterday 00:00:00–23:59:59 UTC), but the filename uses today's date. If the script runs on Feb 9th, the blob will be named `chunk_dataframe_20260209.parquet`, even though it contains Feb 8th's data.
- **No confirmation in force mode**: With `--force`, the overwrite happens without any user prompt.

## Grafana query performance

The pipeline retrieves data for the **previous full day** (yesterday 00:00:00 to 23:59:59 UTC). Depending on the query, fetching a full day of data can be expensive and may result in slow responses or timeouts (the HTTP timeout is set to 30 seconds per query).

### Before adding a new query

Before adding a query to `configs/queries.yaml`, make sure it has been **validated and optimized directly in Grafana** first:

1. **Test the query manually in Grafana** with a 24h time range. If it takes more than a few seconds to return, it will likely cause issues in the pipeline.
2. **Watch out for high-cardinality queries**: queries that fan out across many label combinations (e.g. no label filter, or `{__name__=~".+"}`) generate massive result sets and can overload the datasource.
3. **Use aggregation functions** (`avg_over_time`, `rate`, `count_over_time`, etc.) with an appropriate range vector (e.g. `[1m]`, `[5m]`) to reduce the volume of data returned.
4. **Scope queries with label selectors** to limit them to the relevant targets only (e.g. `{job="integrations/self"}` rather than selecting all jobs).
5. **Be mindful of the impact on shared datasources**: Grafana, Mimir, and Loki instances are often shared. A heavy query triggered by the pipeline can degrade the experience for other users or dashboards querying the same datasource.

### Retry behavior

The Grafana client retries failed requests up to 3 times with exponential backoff on status codes `429`, `500`, `502`, `503`, `504`. This helps with transient failures but will not save a fundamentally too-expensive query — it will just retry it 3 times before failing.
