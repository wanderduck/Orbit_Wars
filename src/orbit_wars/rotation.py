"""Predict orbiting-planet and comet positions at future steps.

Per E1 line 100 / E3 §Methods:
- Orbiting planets rotate around the sun at ``angular_velocity`` rad/turn (one global value per game).
- Static planets do not rotate.
- ``initial_planets`` from the observation gives the positions at game start.

For comets, positions are explicitly enumerated in ``comets[i].paths`` indexed by ``path_index``.
This module only handles orbiting planets; comet position lookup belongs in
:mod:`orbit_wars.world` since it requires the comet group structure.
"""

from __future__ import annotations

import math

from .geometry import SUN_CENTER, is_static_planet
from .state import Planet

__all__ = ["predict_planet_position"]


def predict_planet_position(
    initial_planet: Planet,
    angular_velocity: float,
    steps_ahead: int,
    *,
    center: tuple[float, float] = SUN_CENTER,
) -> tuple[float, float]:
    """Return (x, y) of a planet ``steps_ahead`` turns into the future.

    Static planets return their initial position regardless of ``steps_ahead``.
    Orbiting planets rotate around ``center`` by ``angular_velocity * steps_ahead`` radians.

    The rotation direction matches Kaggle's env (positive ``angular_velocity`` rotates
    toward increasing angle in the standard math convention; the env may use a
    negation that we'll discover via parity tests in :mod:`tests.test_rotation`).
    """
    if is_static_planet(initial_planet.x, initial_planet.y, initial_planet.radius):
        return initial_planet.x, initial_planet.y

    if steps_ahead == 0 or angular_velocity == 0.0:
        return initial_planet.x, initial_planet.y

    cx, cy = center
    dx = initial_planet.x - cx
    dy = initial_planet.y - cy
    radius = math.hypot(dx, dy)
    if radius == 0.0:
        return initial_planet.x, initial_planet.y

    initial_angle = math.atan2(dy, dx)
    new_angle = initial_angle + angular_velocity * steps_ahead
    return cx + radius * math.cos(new_angle), cy + radius * math.sin(new_angle)
