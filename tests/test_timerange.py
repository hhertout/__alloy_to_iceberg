from datetime import UTC, datetime

from utils.timerange import get_previous_day_range


class TestGetPreviousDayRange:
    """Tests for get_previous_day_range."""

    def test_returns_previous_day_midnight_to_end(self) -> None:
        """Core case: 2 March 14:30 → range is 1 March 00:00–23:59."""
        now = datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC)
        from_ts, to_ts = get_previous_day_range(now)

        expected_start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2026, 3, 1, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_at_midnight_returns_previous_day(self) -> None:
        """At exactly 00:00:00, the previous day should be returned."""
        now = datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)
        from_ts, to_ts = get_previous_day_range(now)

        expected_start = datetime(2026, 5, 9, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2026, 5, 9, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_at_end_of_day(self) -> None:
        """At 23:59:59, the previous day should still be returned."""
        now = datetime(2026, 7, 15, 23, 59, 59, tzinfo=UTC)
        from_ts, to_ts = get_previous_day_range(now)

        expected_start = datetime(2026, 7, 14, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2026, 7, 14, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_cross_month_boundary(self) -> None:
        """1 April → previous day is 31 March."""
        now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
        from_ts, to_ts = get_previous_day_range(now)

        expected_start = datetime(2026, 3, 31, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_cross_year_boundary(self) -> None:
        """1 January → previous day is 31 December of the previous year."""
        now = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        from_ts, to_ts = get_previous_day_range(now)

        expected_start = datetime(2025, 12, 31, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_leap_year(self) -> None:
        """1 March on a leap year → previous day is 29 February."""
        now = datetime(2028, 3, 1, 6, 0, 0, tzinfo=UTC)
        from_ts, to_ts = get_previous_day_range(now)

        expected_start = datetime(2028, 2, 29, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2028, 2, 29, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_range_is_exactly_86399_seconds(self) -> None:
        """The range should span exactly 23h59m59s = 86399 seconds."""
        now = datetime(2026, 6, 15, 10, 0, 0, tzinfo=UTC)
        from_ts, to_ts = get_previous_day_range(now)

        assert to_ts - from_ts == 86399

    def test_from_before_to(self) -> None:
        """from_time should always be strictly before to_time."""
        now = datetime(2026, 8, 20, 3, 15, 0, tzinfo=UTC)
        from_ts, to_ts = get_previous_day_range(now)

        assert from_ts < to_ts

    def test_default_now(self) -> None:
        """Without arguments, should return a valid range for today - 1."""
        from_ts, to_ts = get_previous_day_range()

        assert from_ts < to_ts
        assert to_ts - from_ts == 86399
