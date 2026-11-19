"""Portable compute device resolution across laptops (CPU/MPS) and CUDA VMs."""

from __future__ import annotations

import os


def resolve_device() -> str:
    """Resolve requested compute device without crashing on non-GPU hosts."""
    requested = os.getenv("COMPUTE_DEVICE", "auto").strip().lower()
    if requested in {"cpu", "mps"}:
        return requested
    if requested == "cuda":
        return "cuda"
    return "cpu"


if __name__ == "__main__":
    print(f"Resolved device: {resolve_device()}")
