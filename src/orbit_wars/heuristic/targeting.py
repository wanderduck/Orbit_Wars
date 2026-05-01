"""Per-(src, target) scoring for the heuristic agent.

Lifted from E6's ``target_value`` (synthesis §3, §5.B). Score combines (1) value
of the target (production × remaining-profit turns, with multipliers for
static/hostile/neutral/comet/etc.) divided by (2) cost (ships sent + transit
time × cost weight). Higher score = better.
"""

from __future__ import annotations

from ..geometry import is_static_planet
from ..state import ObservationView, Planet
from ..world import WorldModel
from .config import HeuristicConfig

__all__ = ["TargetCandidate", "score_target"]


from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    """A scored (src, target) pair the strategy may choose to launch."""

    src_id: int
    target_id: int
    angle: float
    eta: int
    ships_needed: int
    score: float


def score_target(
    src: Planet,
    target: Planet,
    eta: int,
    ships_needed: int,
    *,
    view: ObservationView,
    world: WorldModel,
    config: HeuristicConfig,
    mission: str = "capture",
) -> float:
    """Score the (src, target) candidate for ``mission``.

    Mission ∈ {"capture", "snipe", "reinforce"}. Larger score = launch sooner.
    """
    remaining_steps = max(1, world.horizon)  # use horizon as proxy for now-distance until episode end
    turns_profit = max(1, remaining_steps - eta)

    base_value = float(target.production) * turns_profit

    # Static / hostile / neutral multipliers (E6 §target_value)
    static = is_static_planet(target.x, target.y, target.radius)
    is_hostile = target.owner not in (-1, view.player)
    is_neutral = target.owner == -1
    is_comet = view.is_comet(target.id)

    if static:
        base_value *= (
            config.static_neutral_value_mult if is_neutral else config.static_hostile_value_mult
        )
    elif eta < config.opening_turn_limit:
        # rotating during opening is risky
        base_value *= config.rotating_opening_value_mult

    if is_hostile:
        base_value *= (
            config.opening_hostile_target_value_mult
            if eta < config.opening_turn_limit
            else config.hostile_target_value_mult
        )

    if is_neutral and eta < config.early_turn_limit:
        base_value *= config.early_neutral_value_mult

    if is_comet:
        base_value *= config.comet_value_mult

    # Mission-specific multipliers
    if mission == "snipe":
        base_value *= config.snipe_score_mult
    elif mission == "reinforce":
        base_value *= config.reinforce_value_mult

    # Cost denominator (E6: value / (send + turns * cost_w + 1))
    cost_weight = (
        config.attack_cost_turn_weight
        if mission == "capture"
        else config.snipe_cost_turn_weight
        if mission == "snipe"
        else config.reinforce_cost_turn_weight
    )
    denom = ships_needed + eta * cost_weight + 1.0
    return base_value / denom
