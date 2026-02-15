import torch
from typing import Any

def resolve_torch_device(device_cfg: str, log: Any) -> torch.device:
	requested = device_cfg.lower().strip()
	if requested not in {"auto", "cpu", "mps", "cuda"}:
		raise ValueError(
			f"Unsupported pytorch device '{device_cfg}'. Use one of: auto, cpu, mps, cuda"
		)

	if requested == "cpu":
		device = torch.device("cpu")
	elif requested == "cuda":
		if torch.cuda.is_available():
			device = torch.device("cuda")
		else:
			log.warning("PyTorch CUDA requested but not available. Falling back to CPU.")
			device = torch.device("cpu")
	elif requested == "mps":
		if torch.backends.mps.is_available():
			device = torch.device("mps")
		else:
			log.warning("PyTorch MPS requested but not available. Falling back to CPU.")
			device = torch.device("cpu")
	else:
		if torch.cuda.is_available():
			device = torch.device("cuda")
		elif torch.backends.mps.is_available():
			device = torch.device("mps")
		else:
			device = torch.device("cpu")

	log.info(f"PyTorch LSTM using device={device.type}")
	return device