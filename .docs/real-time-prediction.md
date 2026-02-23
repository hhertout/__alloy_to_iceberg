# Real-time prediction architecture

This document describes the architecture for running short-to-medium horizon metric forecasts (10m, 1h) in real time on the internal Grafana observability stack. Predictions are published back to Mimir so Grafana can alert on them alongside live metrics.

## Overview

The pipeline extends the existing batch training workflow with a streaming layer. Alloy forwards scraped metrics to Redpanda in addition to Prometheus. A consumer service maintains a rolling lookback window of recent values, runs inference every 30 seconds, and remote-writes the predicted metrics to Mimir.

```
Grafana stack                  Alloy                    Redpanda
┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Mimir  × 3      │────▶│  scrape (30s)   │────▶│  metrics.raw     │
│  Loki   × 3      │     │                 │     │  (OTLP JSON)     │
│  Tempo  × 3      │     │  otelcol        │     └────────┬─────────┘
│  Alloy  × 4      │     │  .exporter      │              │
└──────────────────┘     │  .kafka         │              │ consume
                         └─────────────────┘              ▼
                                                  ┌──────────────────┐
                                                  │  Python consumer │
                                                  │  lookback buffer │
                                                  │  (Polars, 4-6h)  │
                                                  └────────┬─────────┘
                                                           │ infer (every 30s)
                                                           ▼
                                                  ┌──────────────────┐
                                                  │  PyTorch model   │
                                                  │  horizon: 10m    │
                                                  │  horizon:  1h    │
                                                  └────────┬─────────┘
                                                           │ remote write
                                                           ▼
                                                  ┌──────────────────┐
                                                  │      Mimir       │
                                                  │  dl_obs_pred_*   │
                                                  └────────┬─────────┘
                                                           │
                                                           ▼
                                                     Grafana alerts
```

---

## Lookback window design

This section explains why the input lookback window must be significantly larger than the forecast horizon.

### Lookback vs. horizon relationship

For a forecast horizon H, the effective lookback window should be **4x to 6x H**. For a 1h horizon, that means **4h to 6h of input history**.

The reasons are:

- **Autocorrelation at longer lags:** a memory spike at T-3h can precede a cascade failure at T+1h. A short lookback misses this signal entirely.
- **Feature windows:** rolling statistics (mean, std, rate of change) at 1h window require 1h of data to compute. The existing `FeaturesEngineeringV1` already computes rolling mean and std at 1h, 6h, 12h, and 1d — all of these need their full window in the buffer to be valid at inference time.
- **Trend detection:** distinguishing a slow drift from noise requires enough history to fit a meaningful regression slope. With less than 2h of data, a noisy metric has too few points to separate trend from variance.
- **Model context:** sequence models (LSTM, Transformer) use the full input sequence to build a representation. A longer context allows the model to capture the direction and momentum of a metric, not just its current value.

A short lookback predicting 1h ahead would essentially be a short-term extrapolation. It works on smooth, stationary signals but degrades quickly on anything with variable dynamics — which is exactly what observability metrics exhibit under load.

### Recommended lookback: 4h (adjustable to 6h)

| Horizon | Minimum lookback | Recommended lookback | Max useful lookback |
|---------|-----------------|---------------------|---------------------|
| 10m | 40m | 1h | 2h |
| 1h | 4h | **4h** | 6h |

Start with 4h. Move to 6h if the model underfits or if you observe that signals at 4h-6h lag show meaningful correlation with the target. Beyond 6h, the benefit diminishes fast for 1h-horizon forecasting on observability metrics.

Do not extend the raw sequence window to 24h. `FeaturesEngineeringV1` already provides the model with explicit 24h-level signals through `lag_1d`, `rolling_mean_1d`, `rolling_std_1d`, and hour harmonics. Feeding 2880 raw timesteps (24h at 30s) would be redundant with these features, and prohibitively expensive for Transformer self-attention on CPU (attention scales as O(seq_len²): 2880² ≈ 8M elements vs. 480² ≈ 230k for 4h — 34× more expensive per layer). The right way to bring 24h information into the model is to ensure the existing daily features are correctly populated at inference time, which the Prometheus pre-fill handles on startup.

### Precision vs. reaction time

A 1h horizon is inherently less precise than a 30m horizon — prediction error grows with the forecast distance. This is a fundamental property of time series forecasting, not a model limitation.

The tradeoff is deliberate: a 30m forecast gives a narrow reaction window (alert fires, operator sees it, diagnoses root cause, acts — in 30 minutes). A 1h forecast gives enough runway to investigate and intervene before the threshold is breached.

For alerting on infrastructure, 1h is the right choice. Precision can be improved over time by retraining with more data and richer features.

### Feature windows available at 4h lookback

The existing `FeaturesEngineeringV1` already computes the features below. All of them compute correctly within a 4h buffer.

| Feature group | Windows used | Valid at 4h lookback |
|---------------|--------------|----------------------|
| Lags | 1m, 2m, 5m, 10m, 30m, 1h | Yes |
| Rolling mean | 5m, 10m, 30m, 1h | Yes |
| Rolling std | 5m, 10m, 30m, 1h | Yes |
| Diff ratio (mean 1h / mean 1d) | 1h (available), 1d (needs Prometheus pre-fill) | Partial |
| Delta z-score | 1h, 1d | Partial (1d needs pre-fill) |
| Hour harmonics | — | Yes |
| Business day | — | Yes |

Features that rely on 6h, 12h, or 1d rolling windows need Prometheus pre-fill on startup to be accurate (refer to the [Cold start](#cold-start-prometheus-pre-fill) section). Without pre-fill, they degrade gracefully to shorter effective windows until the buffer fills.

The daily features (`lag_1d`, `rolling_mean_1d`, `rolling_std_1d`) are the primary mechanism through which the model accesses 24h-level information. They're more efficient than a raw 24h sequence because they compress the relevant signal into a single value per feature rather than requiring the model to attend over 2880 timesteps. Getting these features right at inference time — through pre-fill — matters more than extending the raw lookback beyond 4-6h.

---

## Data volume estimate

The target stack produces a modest volume of data, which drives most sizing decisions.

| Dimension | Value |
|-----------|-------|
| Instances | 13 (3 Mimir + 3 Loki + 3 Tempo + 4 Alloy) |
| Key metrics per instance | ~50 |
| Total series | ~650 |
| Alloy scrape interval | 30s |
| Consumer resampling | 1min (matches `DEFAULT_AGG_INTERVAL_MS = 60_000`) |
| Message size (OTLP JSON) | ~5 KB |
| **Throughput** | **~100 KB/s** |
| Lookback window (4h at 1min) | 240 points/series |
| In-memory buffer (650 series × 240 points) | ~156k rows — trivial for Polars |

This volume is well within Redpanda's capacity for a single-node dev setup. There's no need for complex partitioning or consumer scaling.

## Latency budget

The pipeline targets predictions available in Grafana within a few seconds of each scrape cycle.

| Step | Cumulative latency |
|------|--------------------|
| Scrape completes | T+0s |
| Alloy processes + sends to Redpanda | T+1s |
| Consumer receives message | T+2s |
| Feature engineering (Polars, in-memory) | T+2.1s |
| PyTorch inference (CPU, small model) | T+2.2s |
| Remote write to Mimir | T+3s |
| **Prediction available in Grafana** | **T+4s** |

End-to-end latency stays well under the 30s prediction cadence.

---

## Component design

This section describes the role and configuration of each component.

### Alloy: dual-forwarding

Alloy scrapes the stack targets every 30 seconds and forwards metrics to two destinations in parallel: Prometheus (existing operational pipeline) and Redpanda (real-time prediction pipeline).

The forwarding to Redpanda uses the `otelcol.exporter.kafka` component, which ships metrics in OTLP JSON format. OTLP JSON is preferred over protobuf for this volume because it's human-readable, directly debuggable with `rpk consume`, and requires no schema registration.

Add a dedicated scrape job and Kafka exporter to `.docker/conf.alloy`:

```alloy
// ─── Real-time prediction: scrape stack targets ───
prometheus.scrape "stack_realtime" {
  targets = [
    {__address__ = "mimir-1:8080",  job = "mimir"},
    {__address__ = "mimir-2:8080",  job = "mimir"},
    {__address__ = "mimir-3:8080",  job = "mimir"},
    {__address__ = "loki-1:3100",   job = "loki"},
    {__address__ = "loki-2:3100",   job = "loki"},
    {__address__ = "loki-3:3100",   job = "loki"},
    {__address__ = "tempo-1:3200",  job = "tempo"},
    {__address__ = "tempo-2:3200",  job = "tempo"},
    {__address__ = "tempo-3:3200",  job = "tempo"},
    {__address__ = "alloy-1:12345", job = "alloy"},
    {__address__ = "alloy-2:12345", job = "alloy"},
    {__address__ = "alloy-3:12345", job = "alloy"},
    {__address__ = "alloy-4:12345", job = "alloy"},
  ]
  scrape_interval = "30s"
  forward_to      = [otelcol.receiver.prometheus.realtime.receiver]
}

otelcol.receiver.prometheus "realtime" {
  output {
    metrics = [otelcol.exporter.kafka.redpanda.input]
  }
}

otelcol.exporter.kafka "redpanda" {
  brokers          = ["redpanda:9092"]
  protocol_version = "2.6.0"
  topic            = "metrics.raw"
  encoding         = "otlp_json"

  producer {
    compression       = "snappy"
    max_message_bytes = 1000000
  }
}
```

This keeps the real-time scrape job completely separate from the existing operational pipeline. The existing `prometheus.scrape` and `prometheus.remote_write` blocks are unchanged.

### Redpanda: topic configuration

A single topic is sufficient for this volume. Create it once with `rpk`:

```sh
rpk topic create metrics.raw \
  --partitions 4 \
  --replicas 1 \
  --topic-config retention.ms=28800000
```

| Setting | Value | Rationale |
|---------|-------|-----------|
| Partitions | 4 | One per major service type (mimir, loki, tempo, alloy) |
| Replicas | 1 | Single-node dev setup |
| Retention | **8h** | 6h lookback + 2h margin for cold start replay |
| Encoding | OTLP JSON | Human-readable, debuggable with `rpk consume` |

Retention must cover the full lookback window plus a buffer. With a 6h lookback and 8h retention, the consumer can replay messages from the last 6h on startup instead of waiting for the buffer to fill organically. In practice, the Prometheus pre-fill strategy (refer to the [Cold start](#cold-start-prometheus-pre-fill) section) is faster and preferred over Kafka replay for lookback windows beyond 2h.

Partition by `job` label on the producer side to keep series for the same service on the same partition. This preserves ordering per service type, which matters for the sliding window.

### Consumer: lookback buffer and inference loop

The consumer is a Python asyncio service (`scripts/realtime_predict.py`) that maintains an in-memory Polars DataFrame per metric series and triggers inference every 30 seconds.

```
Consumer internals
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  Startup                                                            │
│    ├── Load model from Azure Blob Storage                           │
│    └── Pre-fill buffer: query Prometheus for last 4h               │
│          (avoids 4h cold start wait)                                │
│                                                                     │
│  Kafka consumer loop (asyncio)                                      │
│    ├── Deserialize OTLP JSON                                        │
│    ├── Append rows to Polars buffer                                 │
│    └── Drop rows older than 4h + 10min tolerance                   │
│                                                                     │
│  Inference loop (every 30s, independent of message arrival)         │
│    ├── Check buffer has ≥ MIN_POINTS (240 points = 2h minimum)      │
│    ├── Extract last 4h from buffer                                  │
│    ├── Feature engineering (src/features/ — same as batch pipeline) │
│    ├── PyTorch forward pass                                         │
│    │     ├── horizon = 10m → output[0]                             │
│    │     └── horizon =  1h → output[1]                             │
│    └── Remote write to Mimir                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Dependencies:**

```sh
uv add confluent-kafka opentelemetry-proto prometheus-remote-write
```

**Consumer group:** `dl-obs-predictor` — a single consumer is sufficient given the volume.

**Train/serve resolution consistency:** the batch training pipeline resamples all data to 1-minute bins (`DEFAULT_AGG_INTERVAL_MS = 60_000` in `configs/constants.py`). Alloy sends 30s data to Kafka, so the consumer must resample incoming messages to 1-minute bins using `group_by_dynamic` before appending to the buffer. Feeding the model a 30s sequence when it was trained on 1-min data would produce a train/serve skew that silently degrades prediction quality. The `sequence_length` config parameter should be set to `240` for real-time inference (4h at 1min), not the batch value of `1440` (1 day at 1min).

**Lookback buffer:** a Polars `DataFrame` with a `timestamp` index and one column per metric series, at 1-minute resolution. The buffer holds 4h + 5min of data to tolerate late or missing scrapes. Rows older than 4h + 5min are dropped after each resampling step.

**Minimum points gate:** inference runs only when the buffer contains at least 120 data points per series (2 hours of 1-min data). Below this threshold, the cycle is skipped and a warning is logged. This prevents the model from predicting on an insufficiently warm buffer, where features like rolling mean over 1h or z-score over 1h would be computed on incomplete windows.

**Inference trigger:** time-based, every 30 seconds, independent of message arrival rate. If new messages haven't arrived yet (for example, a slow scrape), the inference still runs on the existing buffer.

**Feature engineering:** reuses the versioned `src/features/` pattern from the batch pipeline. The same `FeaturesEngineering` base class applies to the lookback buffer, ensuring feature definitions stay consistent between training and serving.

### Prediction cycle timing

The Kafka consumer loop runs continuously in the background and is not part of the inference hot path. By the time the inference trigger fires every 30s, the buffer is already up-to-date.

**Background consumer (between inference cycles):**

| Step | Estimate |
|------|----------|
| `Consumer.poll()` — receive message batch | 1–3ms |
| OTLP JSON deserialize (~20 messages × 5 KB) | 10–20ms |
| Polars `group_by_dynamic` resample to 1min | 3–8ms |
| Buffer append + drop old rows | 2–5ms |
| **Total per 30s Kafka cycle** | **16–36ms** |

**Inference cycle (every 30s, on the hot path):**

| Step | P50 | P95 | Notes |
|------|-----|-----|-------|
| Buffer snapshot (filter last 4h) | 1ms | 2ms | Polars filter on 156k rows |
| Feature engineering (240 rows) | 15ms | 30ms | Rolling ops, lags, z-scores — dominant cost |
| `select` + `to_numpy()` | 1ms | 2ms | Column selection + NumPy conversion |
| Standardization | <1ms | 1ms | Vectorized NumPy, negligible |
| LSTM forward pass (CPU) | 3ms | 12ms | `hidden=64`, `layers=2`, `seq_len=240`, `input≈80` |
| Transformer forward pass (CPU) | 5ms | 20ms | `d_model=64`, `n_heads=4`, `n_layers=2`, `seq_len=240` |
| Remote write to Mimir | 8ms | 20ms | Protobuf + Snappy + HTTP POST |
| **Total (LSTM)** | **~28ms** | **~67ms** | |
| **Total (Transformer)** | **~30ms** | **~75ms** | |

Both model variants complete comfortably within the 30s inference cadence, with a margin above 99% at roughly 100ms. The **dominant cost is feature engineering** (~50% of total), not the model forward pass. The LSTM and Transformer are both very fast at this scale (`hidden=64`, `seq_len=240`).

The remote write cost depends on network conditions and Mimir load. On a local or same-datacenter deployment it stays below 20ms at P95; across a WAN it could reach 50–80ms, which remains within budget.

If feature engineering ever becomes a bottleneck (>500ms), the optimization is incremental computation: maintain running rolling statistics as new 1-min bins arrive, rather than recomputing the full window each cycle. This would reduce feature engineering to <5ms at the cost of more complex state management.

### Cold start: Prometheus pre-fill

The main challenge of a 4h lookback window is that a freshly started consumer would need to wait 4 hours before making its first prediction.

The solution is to pre-fill the buffer from Prometheus on startup, before connecting to Kafka.

```python
# On startup, before starting the Kafka consumer loop:
# 1. Query Prometheus for the last 2h of each target metric
# 2. Convert the result to a Polars DataFrame
# 3. Populate the in-memory buffer
# 4. Then start consuming from Kafka (latest offset)
```

```sh
# Prometheus range query used for pre-fill (step=1m to match training resolution)
GET /api/v1/query_range?query=<metric>&start=now-4h&end=now&step=60s
```

After pre-fill, the consumer sets the Kafka consumer to start from the latest offset. The buffer stays up-to-date from that point via the Kafka stream.

An alternative to Prometheus pre-fill is to **seek to the 4h-ago offset** in Redpanda on startup, since the topic retains 8h of data. This avoids the Prometheus dependency but requires the consumer to have been absent for less than 8h. For a restart scenario, replaying from Redpanda is simpler and preferred over Prometheus pre-fill when the gap is short.

### Model: architecture recommendation

Two architecture families are well-suited for this forecasting task: LSTM and Transformer. Both take a fixed-length lookback sequence as input and produce two horizon predictions in a single forward pass.

#### Input and output shape

The model receives a sequence of 240 timesteps (4h at 1-min resolution) and outputs two scalar predictions simultaneously.

```
Input:  (batch, seq_len=240, n_features=F)
Output: (batch, 2)                          # [pred_10m, pred_1h]
```

This is a **direct multi-step forecast**: both horizons are predicted in one forward pass rather than step by step. Autoregressive approaches (predict one step, feed it back as input, repeat) accumulate error at each step and are unsuitable for a 1h horizon.

#### Option 1 — LSTM

An LSTM processes the sequence step by step, maintaining a hidden state that carries information forward across timesteps. The last hidden state summarises the full sequence and is fed to a linear head that produces the two horizon outputs.

```
Input sequence (240 steps)
    │
    ▼
LSTM (hidden=64, layers=2, dropout=0.1)
    │ processes timesteps sequentially
    ▼
Last hidden state → (batch, hidden=64)
    │
    ▼
Linear head → (batch, 2)   # [pred_10m, pred_1h]
```

The LSTM's main weakness at a 1h horizon is gradient flow: backpropagating through 240 sequential steps causes vanishing gradients, which limits the model's ability to learn dependencies between distant timesteps. In practice, explicit lag features (lag at 1h, 12h, 1d) compensate for this — the model doesn't need to learn long-range dependencies from the raw sequence because the features make them explicit.

Keep the model small. A large hidden state overfits quickly on a moderate dataset and slows CPU inference unnecessarily.

#### Option 2 — Transformer (encoder-only)

A Transformer encoder replaces the sequential hidden state with a self-attention mechanism. Every timestep attends directly to every other timestep in the sequence, regardless of distance. This eliminates the vanishing gradient problem and makes the Transformer better suited than an LSTM for capturing patterns at the 1h horizon.

```
Input sequence (240 steps)
    │
    ▼
Linear projection → d_model=64
    │
    ▼
Sinusoidal positional encoding
    │  (attention ignores order by default — encoding restores it)
    ▼
TransformerEncoder (n_layers=2, n_heads=4, dim_feedforward=128, dropout=0.1)
    │
    ▼
Global average pooling over seq_len → (batch, d_model=64)
    │  (aggregates all timesteps, more natural than taking only the last one)
    ▼
Linear head → (batch, 2)   # [pred_10m, pred_1h]
```

Keep the model small: `d_model=64`, 2 layers, 4 heads. The dataset is moderate in size and inference runs on CPU every 30s. An oversized Transformer overfits and is slow.

The Transformer will generally outperform the LSTM on the 1h horizon as the training dataset grows — with several months of daily chunks, it has enough data to generalise well.

#### Recommendation

Start with the LSTM. It's a simpler architecture to train and debug, and the explicit lag features compensate for its long-range limitations. Move to the Transformer if the 1h-horizon predictions show systematic bias or high error in evaluation.

Train a single shared model across all target metrics rather than one model per metric. A shared model generalises better when metrics are correlated — Loki ingestion rate correlates with Mimir write pressure, Alloy queue length correlates with scrape duration, and so on. Split per metric only if evaluation shows that some metrics pull the shared model in conflicting directions.

### Output: predicted metrics in Mimir

Predictions are published to Mimir using the Prometheus Remote Write v1 protocol. Each predicted value becomes a separate time series with a `horizon` label.

**Metric naming convention:**

```
dl_obs_predicted_{original_metric_name}
```

**Labels:**

| Label | Example | Description |
|-------|---------|-------------|
| `horizon` | `10m`, `1h` | Prediction look-ahead window |
| `job` | `mimir`, `loki` | Source service |
| `instance` | `mimir-1:8080` | Source instance |

**Example series:**

```promql
dl_obs_predicted_mimir_request_duration_seconds{horizon="10m", job="mimir", instance="mimir-1:8080"}
dl_obs_predicted_mimir_request_duration_seconds{horizon="1h",  job="mimir", instance="mimir-1:8080"}
dl_obs_predicted_alloy_queue_length{horizon="10m", job="alloy", instance="alloy-1:12345"}
dl_obs_predicted_alloy_queue_length{horizon="1h",  job="alloy", instance="alloy-1:12345"}
```

The timestamp on each predicted data point is the current wall-clock time (when inference runs), not the future timestamp. Grafana interprets the `horizon` label to distinguish near-term from medium-term forecasts.

**Remote write endpoint:**

```sh
# Mimir remote write
POST http://<MIMIR_HOST>/api/v1/push
```

Use `snappy` compression and the binary protobuf format for the remote write payload, which is the standard expected by Mimir.

---

## Alerting in Grafana

With predicted metrics in Mimir, you can define Grafana alerts that fire before a threshold is breached.

**Example alert rule (Grafana Alerting):**

```yaml
# Alert when Alloy queue is predicted to saturate within 1 hour
name: AlloyQueueSaturationPredicted1h
expr: |
  dl_obs_predicted_alloy_queue_length{horizon="1h"} > 0.8
for: 2m
labels:
  severity: warning
annotations:
  summary: "Alloy queue predicted to reach {{ $value | humanize }} in 1h"

# Alert when Alloy queue is predicted to saturate within 10 minutes (critical)
name: AlloyQueueSaturationPredicted10m
expr: |
  dl_obs_predicted_alloy_queue_length{horizon="10m"} > 0.8
for: 1m
labels:
  severity: critical
annotations:
  summary: "Alloy queue predicted to reach {{ $value | humanize }} in 10m"
```

Use both horizons together to express alert urgency: the 1h forecast fires a `warning` with time to investigate; the 10m forecast fires a `critical` if the situation has not been resolved. This gives a natural escalation path without requiring a separate alerting pipeline.

Pair predicted alerts with live metric panels to make the forecasts visible alongside actuals:

```promql
# Panel: Alloy queue — actual vs predicted
alloy_queue_length                                              # actual (live)
dl_obs_predicted_alloy_queue_length{horizon="10m"}             # predicted +10m
dl_obs_predicted_alloy_queue_length{horizon="1h"}              # predicted +1h
```

---

## Deployment considerations

This section covers operational details for running the consumer service.

**Hardware requirements:** a CPU is sufficient for the real-time prediction pipeline. No GPU is needed.

GPU throughput is designed for high-volume parallel batching — thousands of requests processed simultaneously to amortise the cost of data transfers between RAM and VRAM. This pipeline runs a single inference every 30 seconds at `batch_size=1`. At that cadence, even a large model comfortably completes its forward pass on CPU well within the 30s budget, and a GPU would add kernel launch and transfer overhead without any throughput benefit. The bottleneck is feature engineering (Polars rolling operations), not the model forward pass.

**Process model:** the consumer runs as a long-lived Python process. Deploy it as a Docker container or a systemd service alongside the existing stack.

**Cold start:** on startup, the consumer pre-fills the buffer from Prometheus (last 4h via range query), then connects to Kafka at the latest offset. The first inference cycle runs as soon as pre-fill completes — typically within a few seconds. The minimum points gate (240 points) ensures predictions don't start on an incomplete buffer.

**Model reload:** the consumer loads the model from Azure Blob Storage at startup and periodically checks for a newer version (for example, every hour). If a new model is available, it reloads in-process without restarting.

**Failure modes:**

| Failure | Behaviour |
|---------|-----------|
| Redpanda unavailable | Consumer retries with exponential backoff; buffer stays valid; no new data ingested |
| Mimir unavailable | Remote write retries with exponential backoff; inference continues |
| Prometheus pre-fill fails | Consumer falls back to Kafka replay (seeks to 4h-ago offset); logs a warning |
| Model inference error | Log the error, skip the cycle, continue consuming |
| Buffer below MIN_POINTS | Skip inference cycle, log a warning |

---

## Next steps

- [Architecture](./architecture.md) — batch training pipeline that produces the model consumed here
- [Local development stack](./local-stack.md) — Docker Compose setup including Redpanda
- [Redpanda documentation](https://docs.redpanda.com) — topic configuration and `rpk` CLI reference
- [Grafana Alerting](https://grafana.com/docs/grafana/latest/alerting/) — alert rule configuration
- [Grafana Alloy Kafka exporter](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.exporter.kafka/) — `otelcol.exporter.kafka` component reference
