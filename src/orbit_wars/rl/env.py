"""Gymnasium env wrapper around the heuristic-substrate :class:`WorldModel`.

Stub for v1. Real implementation in v2: wraps a fast Python simulator for
parallel rollouts. For now, the class signature is here as a placeholder.
"""

from __future__ import annotations

import gymnasium as gym

__all__ = ["OrbitWarsEnv"]


class OrbitWarsEnv(gym.Env):  # type: ignore[misc]
    """Gymnasium env for Orbit Wars. Stub — implementation in v2."""

    def __init__(self) -> None:
        raise NotImplementedError("OrbitWarsEnv is a v2 deliverable; not built yet.")
