"""Heuristic v1 strategy. Public entrypoint: :func:`orbit_wars.heuristic.strategy.agent`.

Sub-modules:
- :mod:`config`     — `HeuristicConfig` dataclass (all tunable constants).
- :mod:`pathing`    — sun-aware angle selection.
- :mod:`targeting`  — per-(src,target) scoring.
- :mod:`sizing`     — fleet-size selection.
- :mod:`threats`    — incoming-fleet projection + defense priority.
- :mod:`comets`     — comet capture timing (v1.1).
- :mod:`strategy`   — top-level :func:`agent(obs)`.
"""

from .strategy import agent

__all__ = ["agent"]
