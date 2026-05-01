"""Fleet-size selection — how many ships to send."""

from __future__ import annotations

import math

from ..state import Planet
from ..world import WorldModel
from .config import HeuristicConfig

__all__ = ["ships_needed_to_capture"]


def ships_needed_to_capture(
    src: Planet,
    target: Planet,
    arrival_turn: int,
    *,
    world: WorldModel,
    player: int,
    config: HeuristicConfig,
) -> int | None:
    """Compute the minimum ships from ``src`` that capture ``target`` at ``arrival_turn``.

    Wraps :meth:`WorldModel.min_ships_to_own_by` to expose a single entry point with
    a sensible safety margin and source-budget cap. Returns ``None`` if uncapturable
    or if the source can't afford the cost.
    """
    raw_need = world.min_ships_to_own_by(
        target_id=target.id,
        eval_turn=arrival_turn,
        attacker_owner=player,
        arrival_turn=arrival_turn,
    )
    if raw_need is None:
        return None
    if raw_need <= 0:
        return None  # already ours at arrival_turn

    # Add safety margin and apply min_launch floor for fleet-speed efficiency
    desired = max(raw_need + config.safety_margin, config.min_launch)
    available = max(0, int(src.ships) - config.home_reserve)
    if desired > available:
        return None
    return int(math.ceil(desired))
