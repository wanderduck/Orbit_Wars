"""Heuristic v1.5 strategy. Public entrypoint: :func:`orbit_wars.heuristic.strategy.agent`.

Sub-modules:
- :mod:`config`   — :class:`HeuristicConfig` dataclass (tunable constants).
- :mod:`strategy` — top-level :func:`agent(obs)` plus defense + Hungarian dispatch.

Dead modules (``pathing``, ``targeting``, ``sizing``, ``threats``, ``comets``)
were deleted in v1.5 — their logic now lives directly in ``strategy.py`` with
the up-to-date API. If you find yourself wanting to add helpers, prefer keeping
them in ``strategy.py`` until the file becomes unwieldy, then split.
"""

from .strategy import agent

__all__ = ["agent"]
