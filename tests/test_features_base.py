from datetime import UTC, datetime

import polars as pl
import pytest

from src.features.base import FeaturesEngineering


class _TestFeatures(FeaturesEngineering):
    def _get_pipes(self) -> list:
        return []


def _to_epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


class TestBaseSeasonality:
    def test_get_hour_seasonality_values(self) -> None:
        fe = _TestFeatures()
        df = pl.DataFrame(
            {
                "timestamp": [
                    _to_epoch_ms(datetime(2026, 3, 2, 0, 0, 0, tzinfo=UTC)),
                    _to_epoch_ms(datetime(2026, 3, 2, 6, 0, 0, tzinfo=UTC)),
                    _to_epoch_ms(datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)),
                ]
            }
        )

        out = fe.get_hour_seasonality(df)

        assert "hour" not in out.columns
        assert "hour_radian" not in out.columns

        assert out["hour_sin"][0] == pytest.approx(0.0, abs=1e-6)
        assert out["hour_cos"][0] == pytest.approx(1.0, abs=1e-6)

        assert out["hour_sin"][1] == pytest.approx(1.0, abs=1e-6)
        assert out["hour_cos"][1] == pytest.approx(0.0, abs=1e-6)

        assert out["hour_sin"][2] == pytest.approx(0.0, abs=1e-6)
        assert out["hour_cos"][2] == pytest.approx(-1.0, abs=1e-6)

    def test_get_week_seasonality_values(self) -> None:
        fe = _TestFeatures()
        df = pl.DataFrame(
            {
                "timestamp": [
                    _to_epoch_ms(datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)),  # Monday
                    _to_epoch_ms(datetime(2026, 3, 3, 12, 0, 0, tzinfo=UTC)),  # Tuesday
                    _to_epoch_ms(datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC)),  # Sunday
                ]
            }
        )

        out = fe.get_week_seasonality(df)

        assert "day_of_week" not in out.columns
        assert "day_of_week_radian" not in out.columns

        # Monday (1): sin ≈ 0.782, cos ≈ 0.623
        assert out["day_of_week_sin"][0] == pytest.approx(0.782, abs=1e-3)
        assert out["day_of_week_cos"][0] == pytest.approx(0.623, abs=1e-3)

        # Tuesday (2): sin ≈ 0.975, cos ≈ -0.223
        assert out["day_of_week_sin"][1] == pytest.approx(0.975, abs=1e-3)
        assert out["day_of_week_cos"][1] == pytest.approx(-0.223, abs=1e-3)

        # Sunday (7): sin ≈ 0.000, cos ≈ 1.000
        assert out["day_of_week_sin"][2] == pytest.approx(0.000, abs=1e-3)
        assert out["day_of_week_cos"][2] == pytest.approx(1.000, abs=1e-3)
