from datetime import UTC, datetime

from utils.timerange import get_previous_day_range


class _FrozenDateTime(datetime):
    frozen_now = datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.frozen_now
        return cls.frozen_now.astimezone(tz)


class TestGetPreviousDayRange:
    """Tests for get_previous_day_range."""

    def _freeze_now(self, monkeypatch, now: datetime) -> None:
        _FrozenDateTime.frozen_now = now
        monkeypatch.setattr("utils.timerange.datetime", _FrozenDateTime)

    def test_returns_previous_day_midnight_to_end(self, monkeypatch) -> None:
        self._freeze_now(monkeypatch, datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC))
        from_ts, to_ts = get_previous_day_range()

        expected_start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2026, 3, 1, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_offset_days_one(self, monkeypatch) -> None:
        self._freeze_now(monkeypatch, datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC))
        from_ts, to_ts = get_previous_day_range(offset_days=1)

        expected_start = datetime(2026, 2, 28, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2026, 2, 28, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_offset_days_negative_one(self, monkeypatch) -> None:
        self._freeze_now(monkeypatch, datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC))
        from_ts, to_ts = get_previous_day_range(offset_days=-1)

        expected_start = datetime(2026, 3, 2, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2026, 3, 2, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_cross_year_boundary(self, monkeypatch) -> None:
        self._freeze_now(monkeypatch, datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC))
        from_ts, to_ts = get_previous_day_range()

        expected_start = datetime(2025, 12, 31, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_leap_year(self, monkeypatch) -> None:
        self._freeze_now(monkeypatch, datetime(2028, 3, 1, 6, 0, 0, tzinfo=UTC))
        from_ts, to_ts = get_previous_day_range()

        expected_start = datetime(2028, 2, 29, 0, 0, 0, tzinfo=UTC)
        expected_end = datetime(2028, 2, 29, 23, 59, 59, tzinfo=UTC)

        assert from_ts == expected_start.timestamp()
        assert to_ts == expected_end.timestamp()

    def test_range_is_exactly_86399_seconds(self, monkeypatch) -> None:
        self._freeze_now(monkeypatch, datetime(2026, 6, 15, 10, 0, 0, tzinfo=UTC))
        from_ts, to_ts = get_previous_day_range()

        assert to_ts - from_ts == 86399

    def test_from_before_to(self, monkeypatch) -> None:
        self._freeze_now(monkeypatch, datetime(2026, 8, 20, 3, 15, 0, tzinfo=UTC))
        from_ts, to_ts = get_previous_day_range()

        assert from_ts < to_ts
