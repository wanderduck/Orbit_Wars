"""Modal abstraction for remote rollouts.

Stub for v1. Real implementation in v2 if local 2080 Ti throughput becomes
the bottleneck (decision point at week 3 per spec §9). Default mode is local.

Use the ``modal-serverless-gpu`` Claude skill when implementing the Modal worker.
"""

from __future__ import annotations

__all__ = ["RolloutWorker"]


class RolloutWorker:
    """Abstract rollout worker. ``local`` mode runs in-process, ``modal`` farms to Modal."""

    def __init__(self, mode: str = "local") -> None:
        if mode not in {"local", "modal"}:
            raise ValueError(f"mode must be 'local' or 'modal', got {mode!r}")
        if mode == "modal":
            raise NotImplementedError("Modal mode is a v2+ deliverable; use mode='local' for now.")
        self.mode = mode
