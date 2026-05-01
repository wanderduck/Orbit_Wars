"""Orbit Wars Kaggle submission entry point.

The ``agent`` function is imported by the Kaggle harness and called once per
turn. Implementation lives in :mod:`orbit_wars.heuristic.strategy`.
"""

from orbit_wars.heuristic.strategy import agent

__all__ = ["agent"]
