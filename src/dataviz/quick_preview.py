from datetime import UTC, datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl


def visualize_df(df: pl.DataFrame, title: str, cols: list) -> None:
    """Visualizes a Polars DataFrame using Matplotlib."""
    timestamps = [datetime.fromtimestamp(ts / 1000, tz=UTC) for ts in df["timestamp"]]

    fig, ax = plt.subplots(figsize=(10, 6))
    for col in cols:
        ax.plot(timestamps, df[col], marker="o", markersize=2)  # type: ignore[arg-type]
    ax.set_title(title)
    ax.set_xlabel("Timestamp")
    ax.set_ylabel("Value")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()
    ax.legend(cols)
    ax.grid(True)
    plt.tight_layout()
    plt.show()
