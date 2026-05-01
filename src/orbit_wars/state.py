"""Typed wrappers over Kaggle Orbit-Wars observations.

The Kaggle ``orbit_wars`` env exports ``Planet``/``Fleet`` named tuples and a
``CENTER``/``ROTATION_RADIUS_LIMIT`` constants. We re-export those, then add a
single :class:`ObservationView` that handles the dict-or-namespace observation
shape uniformly so call sites don't repeat the ``obs.get(...) if isinstance(obs, dict)``
idiom.

Contract derived from ``docs/internal/findings/E3-game-overview.md`` §Observation
reference and ``E4-agents-overview.md`` §Methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kaggle_environments.envs.orbit_wars.orbit_wars import (
    CENTER,
    ROTATION_RADIUS_LIMIT,
    Fleet,
    Planet,
)

__all__ = [
    "CENTER",
    "ROTATION_RADIUS_LIMIT",
    "Fleet",
    "ObservationView",
    "Planet",
    "obs_get",
]


def obs_get(obs: Any, key: str, default: Any = None) -> Any:
    """Fetch a field from an observation that may be a dict or an attribute namespace.

    Per the agents-overview canonical pattern (E4 lines 235-236): observations
    arrive as a dict in some harnesses and as an attribute-style namespace in
    others. Every read of a Kaggle observation must go through this idiom or
    through :class:`ObservationView`.
    """
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


@dataclass(frozen=True, slots=True)
class ObservationView:
    """Read-only typed view over a Kaggle Orbit-Wars observation.

    Build with :meth:`from_raw`. All fields lazy-cast from the raw obs once;
    downstream code consumes the typed attributes.
    """

    player: int
    planets: tuple[Planet, ...]
    fleets: tuple[Fleet, ...]
    angular_velocity: float
    initial_planets: tuple[Planet, ...]
    comets: tuple[dict[str, Any], ...]
    comet_planet_ids: frozenset[int]
    remaining_overage_time: float
    step: int

    @classmethod
    def from_raw(cls, obs: Any, *, step: int = 0) -> ObservationView:
        raw_planets = obs_get(obs, "planets", []) or []
        raw_fleets = obs_get(obs, "fleets", []) or []
        raw_initial = obs_get(obs, "initial_planets", []) or []
        raw_comets = obs_get(obs, "comets", []) or []
        comet_ids = obs_get(obs, "comet_planet_ids", []) or []

        # kaggle_environments populates obs.step (1-indexed turn). Fall back to
        # the keyword arg only if the env didn't supply one (e.g., synthetic obs in tests).
        obs_step = obs_get(obs, "step", None)
        resolved_step = int(obs_step) if obs_step is not None else int(step)

        return cls(
            player=int(obs_get(obs, "player", 0) or 0),
            planets=tuple(Planet(*p) for p in raw_planets),
            fleets=tuple(Fleet(*f) for f in raw_fleets),
            angular_velocity=float(obs_get(obs, "angular_velocity", 0.0) or 0.0),
            initial_planets=tuple(Planet(*p) for p in raw_initial),
            comets=tuple(dict(c) if not isinstance(c, dict) else c for c in raw_comets),
            comet_planet_ids=frozenset(int(i) for i in comet_ids),
            remaining_overage_time=float(obs_get(obs, "remainingOverageTime", 0.0) or 0.0),
            step=resolved_step,
        )

    @property
    def my_planets(self) -> tuple[Planet, ...]:
        return tuple(p for p in self.planets if p.owner == self.player)

    @property
    def enemy_planets(self) -> tuple[Planet, ...]:
        return tuple(p for p in self.planets if p.owner not in (-1, self.player))

    @property
    def neutral_planets(self) -> tuple[Planet, ...]:
        return tuple(p for p in self.planets if p.owner == -1)

    @property
    def my_fleets(self) -> tuple[Fleet, ...]:
        return tuple(f for f in self.fleets if f.owner == self.player)

    @property
    def enemy_fleets(self) -> tuple[Fleet, ...]:
        return tuple(f for f in self.fleets if f.owner not in (-1, self.player))

    def is_comet(self, planet_id: int) -> bool:
        return planet_id in self.comet_planet_ids

    def planet_by_id(self, planet_id: int) -> Planet | None:
        for p in self.planets:
            if p.id == planet_id:
                return p
        return None

    def initial_by_id(self, planet_id: int) -> Planet | None:
        for p in self.initial_planets:
            if p.id == planet_id:
                return p
        return None
