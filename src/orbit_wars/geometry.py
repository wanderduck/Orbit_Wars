"""Geometry primitives for Orbit Wars: distances, angles, sun avoidance, intercepts.

Lifted and adapted from pilkwang's structured baseline (E6) per synthesis §5.B.
All functions are pure and stateless. Constants match :mod:`kaggle_environments.envs.orbit_wars`:

- Board: 100x100 continuous, origin top-left.
- Sun: centered at (50, 50), radius 10.
- Max fleet speed: 6.0 units/turn.
- Fleet speed law: ``1.0 + (MAX_SPEED - 1.0) * (log(ships) / log(1000))^1.5``.
"""

from __future__ import annotations

import math
from typing import Final

__all__ = [
    "BOARD_SIZE",
    "LAUNCH_CLEARANCE",
    "MAX_SPEED",
    "ROTATION_RADIUS_LIMIT",
    "SUN_CENTER",
    "SUN_RADIUS",
    "SUN_SAFETY",
    "angle_between",
    "dist",
    "fleet_speed",
    "is_static_planet",
    "orbital_radius",
    "point_to_segment_distance",
    "safe_angle_and_distance",
    "segment_hits_sun",
]

BOARD_SIZE: Final[float] = 100.0
SUN_CENTER: Final[tuple[float, float]] = (50.0, 50.0)
SUN_RADIUS: Final[float] = 10.0
SUN_SAFETY: Final[float] = 1.5  # E6 default; reject any fleet path within (SUN_RADIUS + SUN_SAFETY)
MAX_SPEED: Final[float] = 6.0
LAUNCH_CLEARANCE: Final[float] = 0.1  # spawn the fleet just outside the launching planet's radius
ROTATION_RADIUS_LIMIT: Final[float] = 50.0  # `orbital_radius + planet_radius < 50` is the orbiting condition


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    """Euclidean distance between two points."""
    return math.hypot(ax - bx, ay - by)


def angle_between(from_xy: tuple[float, float], to_xy: tuple[float, float]) -> float:
    """Angle from ``from_xy`` to ``to_xy`` in radians (0=right, pi/2=down per E1 line 215)."""
    return math.atan2(to_xy[1] - from_xy[1], to_xy[0] - from_xy[0])


def orbital_radius(x: float, y: float, center: tuple[float, float] = SUN_CENTER) -> float:
    """Distance from a point to the sun center."""
    return dist(x, y, center[0], center[1])


def is_static_planet(x: float, y: float, planet_radius: float) -> bool:
    """A planet is static iff orbital_radius + planet_radius >= ROTATION_RADIUS_LIMIT (E1 line 100)."""
    return orbital_radius(x, y) + planet_radius >= ROTATION_RADIUS_LIMIT


def fleet_speed(ships: float | int) -> float:
    """Fleet speed in units/turn for a fleet of ``ships`` ships.

    Per E1 line 121 / E6 cell 7:
        speed = 1.0 + (MAX_SPEED - 1.0) * (log(ships) / log(1000))^1.5

    1 ship = 1.0/turn; ~500 ships = ~5; ~1000 ships = MAX_SPEED.
    """
    n = int(ships)
    if n <= 1:
        return 1.0
    ratio = max(0.0, min(1.0, math.log(n) / math.log(1000.0)))
    return 1.0 + (MAX_SPEED - 1.0) * (ratio**1.5)


def point_to_segment_distance(
    point: tuple[float, float],
    seg_start: tuple[float, float],
    seg_end: tuple[float, float],
) -> float:
    """Distance from ``point`` to the line segment from ``seg_start`` to ``seg_end``.

    E6 cell 7 verbatim. The continuous-collision check used by :func:`segment_hits_sun`.
    """
    px, py = point
    x1, y1 = seg_start
    x2, y2 = seg_end
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-9:
        return dist(px, py, x1, y1)
    t = ((px - x1) * dx + (py - y1) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    return dist(px, py, closest_x, closest_y)


def segment_hits_sun(
    seg_start: tuple[float, float],
    seg_end: tuple[float, float],
    *,
    sun_center: tuple[float, float] = SUN_CENTER,
    sun_radius: float = SUN_RADIUS,
    safety: float = SUN_SAFETY,
) -> bool:
    """True if the segment from ``seg_start`` to ``seg_end`` passes within ``sun_radius+safety`` of the sun.

    E6 cell 7: ``return point_to_segment_distance(...) < SUN_R + safety``.
    Used to reject sun-blind fleet trajectories.
    """
    return point_to_segment_distance(sun_center, seg_start, seg_end) < sun_radius + safety


def safe_angle_and_distance(
    src_x: float,
    src_y: float,
    src_radius: float,
    target_x: float,
    target_y: float,
    target_radius: float,
    *,
    sun_center: tuple[float, float] = SUN_CENTER,
    sun_radius: float = SUN_RADIUS,
    safety: float = SUN_SAFETY,
    launch_clearance: float = LAUNCH_CLEARANCE,
) -> tuple[float, float] | None:
    """Compute the launch angle and travel distance from a source planet to a target.

    Returns ``(angle, hit_distance)`` if the straight-line path is sun-safe, otherwise ``None``.
    The fleet spawns just outside the source planet's radius (per E1 line 144) and stops at
    contact with the target's radius. Both source and target are treated as point centers
    for the segment check, with the planets' radii pulled in via clearance offsets.

    E6 cell 7 ``safe_angle_and_distance`` adapted to typed signature.
    """
    angle = math.atan2(target_y - src_y, target_x - src_x)
    start_x = src_x + math.cos(angle) * (src_radius + launch_clearance)
    start_y = src_y + math.sin(angle) * (src_radius + launch_clearance)
    raw_dist = dist(src_x, src_y, target_x, target_y)
    hit_distance = max(0.0, raw_dist - (src_radius + launch_clearance) - target_radius)
    end_x = start_x + math.cos(angle) * hit_distance
    end_y = start_y + math.sin(angle) * hit_distance
    if segment_hits_sun((start_x, start_y), (end_x, end_y), sun_center=sun_center, sun_radius=sun_radius, safety=safety):
        return None
    return angle, hit_distance
