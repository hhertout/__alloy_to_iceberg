import numpy as np
import pytest

from src.processing.normalization import (
    apply_standardization,
    fit_standardization,
    standardize_train_eval,
)


class TestNormalization:
    def test_standardize_train_eval_uses_train_stats_only(self) -> None:
        X_train = np.array([[1.0, 10.0], [3.0, 30.0], [5.0, 50.0]], dtype=np.float64)
        X_eval = np.array([[7.0, 70.0]], dtype=np.float64)

        X_train_scaled, X_eval_scaled, stats = standardize_train_eval(X_train, X_eval)

        np.testing.assert_allclose(stats.mean, np.array([3.0, 30.0], dtype=np.float64))
        np.testing.assert_allclose(stats.std, np.array([1.63299316, 16.32993162], dtype=np.float64))
        np.testing.assert_allclose(X_train_scaled.mean(axis=0), np.array([0.0, 0.0]), atol=1e-12)
        np.testing.assert_allclose(X_eval_scaled, np.array([[2.44948974, 2.44948974]]), atol=1e-8)

    def test_fit_standardization_handles_constant_feature(self) -> None:
        X_train = np.array([[1.0, 2.0], [1.0, 4.0], [1.0, 6.0]], dtype=np.float64)

        stats = fit_standardization(X_train)
        X_scaled = apply_standardization(X_train, stats)

        np.testing.assert_allclose(stats.std[0], 1.0)
        np.testing.assert_allclose(X_scaled[:, 0], np.array([0.0, 0.0, 0.0]), atol=1e-12)

    def test_fit_standardization_raises_on_empty_train(self) -> None:
        X_train = np.empty((0, 2), dtype=np.float64)

        with pytest.raises(ValueError, match="at least one row"):
            fit_standardization(X_train)
