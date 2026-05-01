"""Threat detection + defense reinforcement.

For v1: identify my planets that the WorldModel forecasts will be lost (owner
flips away from us) within ``reinforce_max_travel_turns + buffer``. For each,
find the nearest available friendly planet that can ship the deficit. Issue
reinforcement orders BEFORE offensive launches in :mod:`strategy`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import dist
from ..state import ObservationView, Planet
from ..world import WorldModel
from .config import HeuristicConfig
from .pathing import plan_safe_launch

__all__ = ["DefenseOrder", "Threat", "find_threats", "plan_defense"]


@dataclass(frozen=True, slots=True)
class Threat:
    """An owned planet projected to flip ownership during the horizon."""

    planet_id: int
    fall_turn: int  # turn at which ownership first flips
    incoming_owner: int


@dataclass(frozen=True, slots=True)
class DefenseOrder:
    """A reinforcement launch from a source planet to a threatened planet."""

    src_id: int
    target_id: int
    angle: float
    ships: int


def find_threats(view: ObservationView, world: WorldModel) -> list[Threat]:
    """Identify owned planets forecast to flip during the timeline horizon."""
    threats: list[Threat] = []
    player = view.player
    for planet in view.my_planets:
        timeline = world.base_timeline.get(planet.id)
        if timeline is None:
            continue
        for t in range(1, timeline.horizon + 1):
            if timeline.owner_at[t] != player:
                threats.append(Threat(
                    planet_id=planet.id,
                    fall_turn=t,
                    incoming_owner=timeline.owner_at[t],
                ))
                break
    return threats


def plan_defense(
    view: ObservationView,
    world: WorldModel,
    threats: list[Threat],
    *,
    config: HeuristicConfig,
    used_ships: dict[int, int] | None = None,
) -> tuple[list[DefenseOrder], dict[int, int]]:
    """For each threat, attempt to find a sun-safe reinforcement.

    Returns (orders, used_ships) where ``used_ships`` records ships committed
    per source planet so subsequent offensive planning doesn't double-spend.
    """
    if used_ships is None:
        used_ships = {}
    if not config.reinforce_enabled:
        return [], used_ships

    orders: list[DefenseOrder] = []
    my_planets_by_id = {p.id: p for p in view.my_planets}
    target_planets_by_id = {p.id: p for p in view.planets}

    # Sort threats by fall_turn ascending (most urgent first)
    sorted_threats = sorted(threats, key=lambda t: t.fall_turn)

    for threat in sorted_threats:
        target = target_planets_by_id.get(threat.planet_id)
        if target is None:
            continue
        if target.owner != view.player:
            continue  # already lost or never ours; defense is recapture, not in v1
        if threat.fall_turn > config.reinforce_max_travel_turns + 5:
            continue  # too far in future, may not need to act yet

        # Find candidate sources: my other planets sorted by distance (excluding target itself)
        candidates: list[Planet] = []
        for src in view.my_planets:
            if src.id == target.id:
                continue
            available = int(src.ships) - used_ships.get(src.id, 0) - config.home_reserve
            if available < config.min_launch:
                continue
            candidates.append(src)
        candidates.sort(key=lambda s: dist(s.x, s.y, target.x, target.y))

        # For each candidate, see if a sun-safe reinforce is feasible
        chosen_order: DefenseOrder | None = None
        for src in candidates:
            launch = plan_safe_launch(src, target)
            if launch is None:
                continue
            angle, _hit_d = launch

            # How many ships do we need to hold the planet through fall_turn + lookahead?
            hold_until = min(world.horizon, threat.fall_turn + config.reinforce_hold_lookahead)
            need = world.reinforcement_needed_to_hold_until(
                target_id=target.id,
                hold_until=hold_until,
                arrival_turn=1,  # we'll cap to ETA below
                defender=view.player,
            )
            if need is None or need <= 0:
                continue

            available = int(src.ships) - used_ships.get(src.id, 0) - config.home_reserve
            cap = int(int(src.ships) * config.reinforce_max_source_fraction)
            send = min(available, cap, need + config.reinforce_safety_margin)
            if send < config.min_launch:
                continue
            chosen_order = DefenseOrder(
                src_id=src.id, target_id=target.id, angle=angle, ships=send
            )
            used_ships[src.id] = used_ships.get(src.id, 0) + send
            break  # one defender per threat in v1

        if chosen_order is not None:
            orders.append(chosen_order)

    return orders, used_ships
