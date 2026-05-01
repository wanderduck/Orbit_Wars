"""Head-to-head evaluation of an RL checkpoint vs an opponent.

Stub for v1. Real implementation in v2 — runs N episodes via
``kaggle_environments.make("orbit_wars")`` against the heuristic baseline and
returns ``{win_rate, score_margin, episodes}``.

Eval gate (per spec §8.7): an RL checkpoint replaces the heuristic in submission
only when win_rate ≥ 0.60 vs heuristic over 100 episodes.
"""

from __future__ import annotations

__all__ = ["evaluate"]


def evaluate(checkpoint: str, opponent: str = "heuristic", n_episodes: int = 100) -> dict[str, float]:
    """Run head-to-head evaluation. Stub — v2 work."""
    raise NotImplementedError("RL evaluation is a v2 deliverable; not built yet.")
