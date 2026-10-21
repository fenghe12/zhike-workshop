"""PyTorch accelerator selection for CPU, NVIDIA CUDA, and Ascend NPU."""

from __future__ import annotations

import contextlib
import os


def select_device(index: int = 0) -> str:
    import torch

    requested = os.environ.get("SMARTCOURSE_DEVICE", "").strip().lower()
    if requested:
        if requested.startswith("npu"):
            try:
                import torch_npu  # noqa: F401
            except ImportError as exc:
                raise RuntimeError("SMARTCOURSE_DEVICE requests NPU, but torch_npu is unavailable") from exc
        return requested

    try:
        import torch_npu  # noqa: F401
    except ImportError:
        pass
    if hasattr(torch, "npu") and torch.npu.is_available():
        return f"npu:{index}"
    if torch.cuda.is_available():
        return f"cuda:{index}"
    return "cpu"


def accelerator_context(device: str):
    import torch

    if device.startswith("npu") and hasattr(torch, "npu"):
        return torch.npu.device(device)
    if device.startswith("cuda"):
        return torch.cuda.device(device)
    return contextlib.nullcontext()


def empty_accelerator_cache() -> None:
    import torch

    if hasattr(torch, "npu") and torch.npu.is_available():
        torch.npu.empty_cache()
    elif torch.cuda.is_available():
        torch.cuda.empty_cache()
