"""Utilities for computing time ranges used by the data pipeline."""

from datetime import UTC, datetime, timedelta


def get_previous_day_range(offset_days: int = 0) -> tuple[float, float]:
    """Return the full previous day as a (from_time, to_time) tuple of Unix timestamps.

    The range covers **yesterday 00:00:00 UTC** (inclusive) to
    **yesterday 23:59:59 UTC** (inclusive), regardless of the current time.

    Args:
        offset_days: Number of days to offset from today. Defaults to 0 (yesterday).
                     Can be negative to get future days.

    Returns:
        A tuple ``(from_timestamp, to_timestamp)`` in **seconds** (Unix epoch).

    Examples:
        If *now* is 2026-03-02 14:30:00 UTC the returned range is:
        - from: 2026-03-01 00:00:00 UTC  →  1740787200.0
        - to:   2026-03-01 23:59:59 UTC  →  1740873599.0
    """
    now = datetime.now(UTC)

    target_day = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=1 + offset_days
    )

    start = target_day  # 00:00:00
    end = target_day.replace(hour=23, minute=59, second=59)  # 23:59:59

    return start.timestamp(), end.timestamp()
