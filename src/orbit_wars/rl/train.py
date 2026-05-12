"""PPO + self-play league training loop. Stub for v1."""
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

    # --- TRAINING SPEED & CONVERGENCE UPGRADES ---
    n_envs: int = 128           # Increased: 32 severely starves modern GPUs
    n_steps: int = 512          # Decreased: Pushes updates faster (every 512 rollout steps)
    batch_size: int = 8192      # Increased: Larger batches stabilize gradients, saturates GPU perfectly
    n_epochs: int = 4           # Decreased: Fewer epochs reduces overfitting on small rollout buffers
    total_steps: int = 50_000_000

def main(*args: object, **kwargs: object) -> None:
    """Entrypoint. Stub — v2 work."""
    raise NotImplementedError("PPO training is a v2 deliverable; not built yet.")