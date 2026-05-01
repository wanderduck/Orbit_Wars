"""Rotation prediction invariants."""

from __future__ import annotations

import math

import pytest

from orbit_wars import rotation
from orbit_wars.geometry import ROTATION_RADIUS_LIMIT
from orbit_wars.state import Planet


def _orbiting_planet(x: float, y: float, radius: float = 2.0) -> Planet:
    return Planet(id=0, owner=-1, x=x, y=y, radius=radius, ships=10, production=2)


class TestRotation:
    def test_static_planet_does_not_move(self) -> None:
        # (98, 50) with radius 2: 48 + 2 = 50 >= ROTATION_RADIUS_LIMIT → static
        p = Planet(id=1, owner=-1, x=98.0, y=50.0, radius=2.0, ships=10, production=2)
        for steps in (0, 1, 50, 500):
            assert rotation.predict_planet_position(p, angular_velocity=0.05, steps_ahead=steps) == (98.0, 50.0)

    def test_zero_steps_returns_initial_position(self) -> None:
        p = _orbiting_planet(60.0, 50.0)
        assert rotation.predict_planet_position(p, angular_velocity=0.05, steps_ahead=0) == (60.0, 50.0)

    def test_zero_angular_velocity_returns_initial_position(self) -> None:
        p = _orbiting_planet(60.0, 50.0)
        assert rotation.predict_planet_position(p, angular_velocity=0.0, steps_ahead=10) == (60.0, 50.0)

    def test_full_revolution_returns_to_start(self) -> None:
        p = _orbiting_planet(60.0, 50.0)
        ang_vel = 0.05
        steps = round(2 * math.pi / ang_vel)
        x, y = rotation.predict_planet_position(p, angular_velocity=ang_vel, steps_ahead=steps)
        assert x == pytest.approx(60.0, abs=0.5)
        assert y == pytest.approx(50.0, abs=0.5)

    def test_quarter_turn_clockwise_or_counter_consistent(self) -> None:
        p = _orbiting_planet(60.0, 50.0)
        ang_vel = 0.05
        steps = round((math.pi / 2) / ang_vel)
        x, y = rotation.predict_planet_position(p, angular_velocity=ang_vel, steps_ahead=steps)
        # After a quarter turn, the planet should be at radius 10 from the sun center
        # but rotated 90 degrees: starts at (60,50) → angle 0 from sun → after pi/2 rotation: (50,60).
        assert x == pytest.approx(50.0, abs=0.5)
        assert y == pytest.approx(60.0, abs=0.5)
