"""Heuristic v2.0 strategy. Public entrypoint: :func:`orbit_wars.heuristic.strategy.agent`.

Sub-modules:
- :mod:`config`   — :class:`HeuristicConfig` dataclass (tunable constants).
- :mod:`strategy` — top-level :func:`agent(obs)` plus Unified optimal Hungarian dispatch.

Version 2.0 introduces a vastly enhanced utility scoring engine that mathematically
integrates all config parameters to prioritize targets optimally.
"""

from .strategy import agent
from .config import HeuristicConfig

__all__ = ["agent", "HeuristicConfig"]