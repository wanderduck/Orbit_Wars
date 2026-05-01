"""Sun-aware pathing wrapper.

For v1, just defers to :func:`orbit_wars.geometry.safe_angle_and_distance`. If
that returns ``None`` (sun blocks the direct line), v1 skips the launch — we do
NOT search for a deflected angle yet (E6's ``search_safe_intercept`` is v1.1
work). This is intentionally conservative: missing some launch opportunities is
strictly better than burning ships on sun collisions.
"""

from __future__ import annotations

from ..geometry import safe_angle_and_distance
from ..state import Planet

__all__ = ["plan_safe_launch"]


def plan_safe_launch(src: Planet, target: Planet) -> tuple[float, float] | None:
    """Return (angle, hit_distance) for a sun-safe direct shot, or ``None`` if blocked.

    For v1.1: add `search_safe_intercept` (E6 cell 7) for around-the-sun deflection.
    """
    return safe_angle_and_distance(
        src.x, src.y, src.radius,
        target.x, target.y, target.radius,
    )
