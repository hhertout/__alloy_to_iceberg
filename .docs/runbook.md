# Runbook

## Blob Storage: overwrite behavior

The Azure Blob Storage upload uses `overwrite=True`. This means the upload **silently replaces any blob with the same name** — no versioning, no backup, no warning.

Because the blob naming convention is date-based (`chunks/chunk_dataframe_YYYYMMDD.parquet`), running the pipeline **multiple times on the same day overwrites the previous chunk** with the latest data. Only the last run of the day is kept.

### What to watch out for

- **Multiple runs per day:** If you trigger the script more than once in a given day (manually or via CI/CD), the earlier run's data is lost. There's no append or deduplication logic — the upload fully replaces the file.
- **File naming is tied to the current date** (`time.strftime("%Y%m%d")`), not to the data's time range. The data covers the **previous day** (yesterday 00:00:00–23:59:59 UTC), but the filename uses today's date. If you run the script on Feb 9th, the blob is named `chunk_dataframe_20260209.parquet`, even though it contains Feb 8th's data.
- **No confirmation in force mode:** With `--force`, the overwrite happens without any user prompt.

## Grafana query performance

The pipeline retrieves data for the **previous full day** (yesterday 00:00:00 to 23:59:59 UTC). Depending on the query, fetching a full day of data can be expensive and may result in slow responses or timeouts (the HTTP timeout is 30 seconds per query).

### Before adding a new query

Before you add a query to `configs/queries.yaml`, **validate and optimize it directly in Grafana** first:

1. **Test the query manually in Grafana** with a 24h time range. If it takes more than a few seconds to return, it will likely cause issues in the pipeline.
2. **Watch out for high-cardinality queries:** Queries that fan out across many label combinations (for example, no label filter, or `{__name__=~".+"}`) generate massive result sets and can overload the datasource.
3. **Use aggregation functions** (`avg_over_time`, `rate`, `count_over_time`, etc.) with an appropriate range vector (for example, `[1m]`, `[5m]`) to reduce the volume of data returned.
4. **Scope queries with label selectors** to limit them to the relevant targets only (for example, `{job="integrations/self"}` rather than selecting all jobs).
5. **Be mindful of the impact on shared datasources:** Grafana, Mimir, and Loki instances are often shared. A heavy query triggered by the pipeline can degrade the experience for other users or dashboards querying the same datasource.

### Retry behavior

The Grafana client retries failed requests up to 3 times with exponential backoff on status codes `429`, `500`, `502`, `503`, `504`. This helps with transient failures but doesn't save a fundamentally too-expensive query — it just retries it 3 times before failing.
