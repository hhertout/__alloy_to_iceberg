from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class StandardizationStats:
    mean: NDArray[np.float64]
    std: NDArray[np.float64]


def fit_standardization(
    X_train: NDArray[np.float64], epsilon: float = 1e-12
) -> StandardizationStats:
    if X_train.ndim != 2:
        raise ValueError("X_train must be a 2D array")
    if X_train.shape[0] == 0:
        raise ValueError("X_train must contain at least one row")

    X_train_f = X_train.astype(np.float64, copy=False)
    mean = X_train_f.mean(axis=0, dtype=np.float64)
    std = X_train_f.std(axis=0, dtype=np.float64)
    safe_std = np.where(std < epsilon, 1.0, std)

    return StandardizationStats(mean=mean, std=safe_std)


def apply_standardization(
    X: NDArray[np.float64], stats: StandardizationStats
) -> NDArray[np.float64]:
    X_f = X.astype(np.float64, copy=False)
    return (X_f - stats.mean) / stats.std


def standardize_train_eval(
    X_train: NDArray[np.float64], X_eval: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], StandardizationStats]:
    stats = fit_standardization(X_train)
    X_train_scaled = apply_standardization(X_train, stats)
    X_eval_scaled = apply_standardization(X_eval, stats)
    return X_train_scaled, X_eval_scaled, stats
