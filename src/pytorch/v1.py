import copy
import time
from typing import Any, cast

import numpy as np
import polars as pl
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error
from torch import nn
from torch.utils.data import DataLoader, Dataset

from configs.base import load_limits_settings, load_model_settings
from src.processing.normalization import apply_standardization, standardize_train_eval
from src.processing.split_df_for_training import split_df_for_training
from utils.logging import get_logger
from src.pytorch.device import resolve_torch_device


class _LSTMRegressor(nn.Module):
	def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float) -> None:
		super().__init__()
		effective_dropout = dropout if num_layers > 1 else 0.0
		self.lstm = nn.LSTM(
			input_size=input_size,
			hidden_size=hidden_size,
			num_layers=num_layers,
			batch_first=True,
			dropout=effective_dropout,
		)
		self.head = nn.Linear(hidden_size, 1)

	def forward(self, x: torch.Tensor) -> torch.Tensor:
		out, _ = self.lstm(x)
		last = out[:, -1, :]
		pred = self.head(last)
		return cast(torch.Tensor, pred.squeeze(-1))


class _SequenceDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
	def __init__(self, X: np.ndarray, y: np.ndarray, sequence_length: int) -> None:
		self.X = X.astype(np.float32, copy=False)
		self.y = y.astype(np.float32, copy=False)
		self.sequence_length = sequence_length

	def __len__(self) -> int:
		return max(0, len(self.X) - self.sequence_length)

	def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
		end = index + self.sequence_length
		x = torch.from_numpy(self.X[index:end])
		y = torch.tensor(self.y[end], dtype=torch.float32)
		return x, y


def _filter_finite_rows(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
	mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
	dropped = int((~mask).sum())
	return X[mask], y[mask], dropped


def _predict_batched(model: nn.Module, loader: DataLoader[Any], device: torch.device) -> np.ndarray:
	preds: list[np.ndarray] = []
	model.eval()
	with torch.no_grad():
		for batch_X, _ in loader:
			batch_X = batch_X.to(device)
			batch_pred = model(batch_X).detach().cpu().numpy().astype(np.float64)
			preds.append(batch_pred)
	if not preds:
		return np.empty((0,), dtype=np.float64)
	return np.concatenate(preds)


def _standardize_target(y_train: np.ndarray, y_val: np.ndarray, y_test: np.ndarray) -> tuple[
	np.ndarray, np.ndarray, np.ndarray, float, float
]:
	y_mean = float(np.mean(y_train))
	y_std = float(np.std(y_train))
	if not np.isfinite(y_std) or y_std < 1e-8:
		y_std = 1.0

	y_train_s = ((y_train - y_mean) / y_std).astype(np.float32, copy=False)
	y_val_s = ((y_val - y_mean) / y_std).astype(np.float32, copy=False)
	y_test_s = ((y_test - y_mean) / y_std).astype(np.float32, copy=False)
	return y_train_s, y_val_s, y_test_s, y_mean, y_std


def pytorch_train_lstm(df: pl.DataFrame) -> tuple[Any, dict[str, float]]:
	start = time.time()
	log = get_logger("generate_model")

	model_settings = load_model_settings()
	limits_settings = load_limits_settings()
	pt = model_settings.pytorch
	device = resolve_torch_device(pt.device, log)

	torch.manual_seed(pt.random_seed)
	np.random.seed(pt.random_seed)

	training_df, val_df, test_df = split_df_for_training(df)
	target_col = limits_settings.target_column_name
	feature_cols = [col for col in df.columns if col != target_col]

	X_train = training_df.select(feature_cols).to_numpy()
	y_train = training_df.select(target_col).to_numpy().ravel()
	X_val = val_df.select(feature_cols).to_numpy()
	y_val = val_df.select(target_col).to_numpy().ravel()
	X_test = test_df.select(feature_cols).to_numpy()
	y_test = test_df.select(target_col).to_numpy().ravel()

	X_train, y_train, dropped_train = _filter_finite_rows(X_train, y_train)
	X_val, y_val, dropped_val = _filter_finite_rows(X_val, y_val)
	X_test, y_test, dropped_test = _filter_finite_rows(X_test, y_test)

	if dropped_train + dropped_val + dropped_test > 0:
		log.info(
			f"PyTorch LSTM dropped non-finite rows train={dropped_train}, val={dropped_val}, test={dropped_test}"
		)

	X_train, X_val, scaling_stats = standardize_train_eval(X_train, X_val)
	X_test = apply_standardization(X_test, scaling_stats)
	y_train_s, y_val_s, y_test_s, y_mean, y_std = _standardize_target(y_train, y_val, y_test)
	X_train = np.clip(X_train, -20.0, 20.0)
	X_val = np.clip(X_val, -20.0, 20.0)
	X_test = np.clip(X_test, -20.0, 20.0)

	train_ds = _SequenceDataset(X_train, y_train_s, pt.sequence_length)
	val_ds = _SequenceDataset(X_val, y_val_s, pt.sequence_length)
	test_ds = _SequenceDataset(X_test, y_test_s, pt.sequence_length)

	if len(train_ds) == 0 or len(val_ds) == 0 or len(test_ds) == 0:
		raise ValueError("Not enough rows to build LSTM sequences. Reduce sequence_length.")

	train_loader = DataLoader(train_ds, batch_size=pt.batch_size, shuffle=True)
	val_loader = DataLoader(val_ds, batch_size=pt.batch_size, shuffle=False)
	test_loader = DataLoader(test_ds, batch_size=pt.batch_size, shuffle=False)

	ensemble_runs = max(1, int(pt.ensemble_runs))
	best_overall_val = float("inf")
	best_model: _LSTMRegressor | None = None
	test_pred_runs_scaled: list[np.ndarray] = []

	log.info(
		f"Training PyTorch LSTM model with {len(train_ds)} sequences and {X_train.shape[1]} features (ensemble_runs={ensemble_runs})..."
	)
	log.info(f"PyTorch LSTM target normalization mean={y_mean:.6f}, std={y_std:.6f}")

	for run_idx in range(ensemble_runs):
		run_seed = pt.random_seed + run_idx
		torch.manual_seed(run_seed)
		np.random.seed(run_seed)

		model = _LSTMRegressor(
			input_size=X_train.shape[1],
			hidden_size=pt.hidden_size,
			num_layers=pt.num_layers,
			dropout=pt.dropout,
		).to(device)
		optimizer = torch.optim.Adam(
			model.parameters(),
			lr=pt.learning_rate,
			weight_decay=pt.weight_decay,
		)
		criterion = nn.SmoothL1Loss()
		scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
			optimizer,
			mode="min",
			factor=0.5,
			patience=max(1, pt.early_stopping_patience // 2),
			min_lr=1e-6,
		)

		best_val = float("inf")
		best_state: dict[str, torch.Tensor] | None = None
		patience_count = 0

		log.info(f"PyTorch LSTM ensemble run {run_idx + 1}/{ensemble_runs} (seed={run_seed})")

		model.train()
		for epoch in range(1, pt.epochs + 1):
			epoch_train_loss_sum = 0.0
			epoch_train_batches = 0
			for batch_X, batch_y in train_loader:
				batch_X = batch_X.to(device)
				batch_y = batch_y.to(device)
				optimizer.zero_grad()
				pred = model(batch_X)
				loss = criterion(pred, batch_y)
				if not torch.isfinite(loss):
					raise ValueError("Non-finite batch loss during LSTM training.")
				loss.backward()
				torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
				optimizer.step()
				epoch_train_loss_sum += float(loss.item())
				epoch_train_batches += 1

			model.eval()
			val_loss_sum = 0.0
			val_batches = 0
			with torch.no_grad():
				for val_batch_X, val_batch_y in val_loader:
					val_batch_X = val_batch_X.to(device)
					val_batch_y = val_batch_y.to(device)
					val_batch_pred = model(val_batch_X)
					val_batch_loss = criterion(val_batch_pred, val_batch_y)
					val_loss_sum += float(val_batch_loss.item())
					val_batches += 1
			val_loss = val_loss_sum / max(1, val_batches)
			scheduler.step(val_loss)

			train_loss = epoch_train_loss_sum / max(1, epoch_train_batches)
			if not np.isfinite(train_loss) or not np.isfinite(val_loss):
				raise ValueError(
					"Non-finite loss detected during LSTM training. Check feature NaN/inf handling and learning rate."
				)
			log.info(
				f"PyTorch LSTM run {run_idx + 1}/{ensemble_runs} epoch {epoch}/{pt.epochs} - train_loss={train_loss:.6f}, val_loss={val_loss:.6f}"
			)

			if val_loss < best_val:
				best_val = val_loss
				best_state = copy.deepcopy(model.state_dict())
				patience_count = 0
			else:
				patience_count += 1
				if patience_count >= pt.early_stopping_patience:
					break

			model.train()

		if best_state is not None:
			model.load_state_dict(best_state)

		test_pred_run_scaled = _predict_batched(model, test_loader, device)
		test_pred_runs_scaled.append(test_pred_run_scaled)

		if best_val < best_overall_val:
			best_overall_val = best_val
			best_model = model

	if not test_pred_runs_scaled:
		raise ValueError("No predictions produced by PyTorch LSTM.")

	if len(test_pred_runs_scaled) == 1:
		test_pred_scaled = test_pred_runs_scaled[0]
	else:
		test_pred_scaled = np.mean(np.vstack(test_pred_runs_scaled), axis=0)

	test_pred = test_pred_scaled * y_std + y_mean
	y_true = y_test[pt.sequence_length :].astype(np.float64)
	mae = mean_absolute_error(y_true, test_pred)
	rmse = np.sqrt(mean_squared_error(y_true, test_pred))
	training_time = time.time() - start

	metrics = {
		"features_number": X_train.shape[1],
		"training_time_seconds": training_time,
		"mae": mae,
		"rmse": rmse,
	}
	if best_model is None:
		raise ValueError("PyTorch LSTM could not produce a trained model.")
	return best_model, metrics

