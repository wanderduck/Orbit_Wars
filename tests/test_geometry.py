"""Geometry invariants. Lightweight; should run in <1s."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from orbit_wars import geometry


class TestFleetSpeed:
    def test_one_ship_is_speed_one(self) -> None:
        assert geometry.fleet_speed(1) == 1.0

    def test_thousand_ships_is_max_speed(self) -> None:
        assert geometry.fleet_speed(1000) == pytest.approx(geometry.MAX_SPEED, abs=1e-6)

    def test_speed_is_monotonic_non_decreasing(self) -> None:
        speeds = [geometry.fleet_speed(n) for n in (1, 2, 10, 50, 100, 500, 1000)]
        assert all(b >= a - 1e-9 for a, b in zip(speeds, speeds[1:]))

    def test_500_ships_around_5(self) -> None:
        # Spec docstring: "~500 ships moves at ~5"
        assert 4.5 < geometry.fleet_speed(500) < 5.5

    @given(ships=st.integers(min_value=1, max_value=10_000))
    def test_speed_in_valid_range(self, ships: int) -> None:
        s = geometry.fleet_speed(ships)
        assert 1.0 <= s <= geometry.MAX_SPEED + 1e-9


class TestDistance:
    @given(
        x1=st.floats(min_value=0.0, max_value=100.0),
        y1=st.floats(min_value=0.0, max_value=100.0),
        x2=st.floats(min_value=0.0, max_value=100.0),
        y2=st.floats(min_value=0.0, max_value=100.0),
    )
    def test_distance_symmetric(self, x1: float, y1: float, x2: float, y2: float) -> None:
        assert geometry.dist(x1, y1, x2, y2) == pytest.approx(geometry.dist(x2, y2, x1, y1))

    def test_distance_self_is_zero(self) -> None:
        assert geometry.dist(50.0, 50.0, 50.0, 50.0) == 0.0


class TestAngle:
    def test_east(self) -> None:
        assert geometry.angle_between((0.0, 0.0), (10.0, 0.0)) == pytest.approx(0.0)

    def test_south(self) -> None:
        assert geometry.angle_between((0.0, 0.0), (0.0, 10.0)) == pytest.approx(math.pi / 2)

    def test_west(self) -> None:
        # atan2 returns pi for negative-x, zero-y; use abs since it could be -pi too
        assert abs(geometry.angle_between((0.0, 0.0), (-10.0, 0.0))) == pytest.approx(math.pi)


class TestSunCollision:
    def test_clear_segment_does_not_hit_sun(self) -> None:
        # Two points far from the sun on the same side
        assert not geometry.segment_hits_sun((10.0, 10.0), (10.0, 90.0))

    def test_segment_through_center_hits_sun(self) -> None:
        # Diagonal that passes through the sun center
        assert geometry.segment_hits_sun((10.0, 10.0), (90.0, 90.0))

    def test_segment_grazing_hits_sun_with_safety(self) -> None:
        # A horizontal segment at y=50 - SUN_RADIUS (just touching the boundary)
        # falls inside (sun_radius + SUN_SAFETY).
        y = 50.0 - geometry.SUN_RADIUS + 0.5  # well inside the safety zone
        assert geometry.segment_hits_sun((10.0, y), (90.0, y))

    def test_safe_distance_outside_safety_zone(self) -> None:
        # Horizontal segment well outside the sun
        y = 50.0 - geometry.SUN_RADIUS - geometry.SUN_SAFETY - 1.0
        assert not geometry.segment_hits_sun((10.0, y), (90.0, y))


class TestSafeAngleAndDistance:
    def test_blocked_by_sun_returns_none(self) -> None:
        # Two planets on opposite sides of the sun on the line through center
        result = geometry.safe_angle_and_distance(
            src_x=10.0, src_y=50.0, src_radius=2.0,
            target_x=90.0, target_y=50.0, target_radius=2.0,
        )
        assert result is None

    def test_clear_line_returns_angle_distance(self) -> None:
        result = geometry.safe_angle_and_distance(
            src_x=10.0, src_y=20.0, src_radius=2.0,
            target_x=90.0, target_y=20.0, target_radius=2.0,
        )
        assert result is not None
        angle, hit_d = result
        assert angle == pytest.approx(0.0, abs=1e-6)
        # Total raw distance 80, minus src.r + clearance + target.r ≈ 80 - 4.1
        assert 75.0 < hit_d < 80.0


class TestStaticPlanet:
    def test_planet_far_from_sun_is_static(self) -> None:
        # (98, 50) is 48 units from sun center; 48 + radius 2 = 50 >= 50 → static
        assert geometry.is_static_planet(98.0, 50.0, planet_radius=2.0)

    def test_planet_at_corner_is_static(self) -> None:
        # (95, 95) is sqrt((95-50)^2 + (95-50)^2) ≈ 63.6 from sun → definitely static
        assert geometry.is_static_planet(95.0, 95.0, planet_radius=2.0)

    def test_planet_near_sun_is_orbiting(self) -> None:
        # Planet at (60, 50) is 10 units from sun; 10 + 2 = 12 < 50 → orbiting
        assert not geometry.is_static_planet(60.0, 50.0, planet_radius=2.0)

    def test_planet_at_threshold_is_static(self) -> None:
        # exactly at the orbital_radius + planet_radius == ROTATION_RADIUS_LIMIT boundary
        # (98, 50) radius 2 → 48 + 2 = 50 — boundary case is STATIC per `>= 50`
        assert geometry.is_static_planet(98.0, 50.0, planet_radius=2.0)
