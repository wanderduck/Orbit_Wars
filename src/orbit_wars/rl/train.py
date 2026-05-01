"""PPO + self-play league training loop.

Stub for v1. Real implementation in v2 with hyperparams from spec §8.4 and
synthesis §5.A. Default hyperparams below match the spec.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["PPOConfig", "main"]


@dataclass(frozen=True, slots=True)
class PPOConfig:
    lr: float = 3e-4
    gamma: float = 0.997
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    entropy_coef: float = 0.01
    value_coef: float = 0.5
    n_envs: int = 32
    n_steps: int = 1024
    batch_size: int = 4096
    n_epochs: int = 6                # spec §8.4
    total_steps: int = 10_000_000


def main(*args: object, **kwargs: object) -> None:
    """Entrypoint. Stub — v2 work."""
    raise NotImplementedError("PPO training is a v2 deliverable; not built yet.")
