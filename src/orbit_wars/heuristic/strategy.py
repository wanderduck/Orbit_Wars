"""Top-level v1 heuristic agent — minimal sniper.

v1 is intentionally minimal: nearest-target sniper with WorldModel-backed
ship sizing for accurate forecasts and sun-aware aiming. No mission
decomposition, no scoring multipliers, no intercept solver. Designed to be
a reliable, debuggable baseline that beats `random` >=80% of the time.

Algorithm:
    For each owned planet (src):
      For each non-owned planet (target), nearest-first:
        If src->target line is sun-safe:
          Compute ships needed via WorldModel.min_ships_to_own_by
          If src has enough ships:
            Launch and break to next src

The WorldModel cross-check accounts for in-flight enemy fleets and target
production during transit. Boundary catch returns ``[]`` on any exception.
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from typing import Any

from ..geometry import dist, is_static_planet, safe_angle_and_distance
from ..state import ObservationView, Planet
from ..world import WorldModel, aim_with_prediction, estimate_fleet_eta, path_collision_predicted
from .config import HeuristicConfig

__all__ = ["LaunchDecision", "agent", "decide_with_decisions"]


@dataclass(frozen=True, slots=True)
class LaunchDecision:
    """Per-launch metadata captured by ``decide_with_decisions``.

    Used by ``tools/diagnostic.py`` to log which target each launch was aimed at,
    so we can later reconcile against the env's actual fleet trajectories and
    diagnose failure modes (sun, miss, combat-loss, target-already-ours, etc).
    """

    src_id: int
    target_id: int
    angle: float
    ships: int
    eta: int
    src_ships_pre_launch: int
    target_ships_at_launch: int
    target_owner: int
    target_x: float
    target_y: float
    target_radius: float
    target_is_static: bool
    target_is_comet: bool

_DEFAULT_CONFIG = HeuristicConfig.default()


def agent(obs: Any, config: HeuristicConfig | None = None) -> list[list[float | int]]:
    """Minimal heuristic v1 agent.

    Note on the ``config`` param: when called by ``kaggle_environments.env.run``,
    the second arg is the env's configuration Struct ({'seed': ..., 'episodeSteps': ...}),
    NOT a HeuristicConfig. We must not treat it as one — earlier we did
    ``cfg = config or _DEFAULT_CONFIG`` which evaluated the truthy Struct as cfg,
    then ``cfg.sim_horizon`` raised AttributeError, was caught silently, and the
    agent returned [] every single turn. That's why baseline was 1W-9L vs random.
    """
    if isinstance(config, HeuristicConfig):
        cfg = config
    else:
        cfg = _DEFAULT_CONFIG
    try:
        return _decide(obs, cfg)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return []


def decide_with_decisions(
    obs: Any,
    cfg: HeuristicConfig | None = None,
) -> tuple[list[list[float | int]], list[LaunchDecision]]:
    """Same algorithm as ``agent``/``_decide``, but also returns per-launch metadata.

    Used by the diagnostic harness in ``tools/diagnostic.py``.  Public so external
    tooling can introspect what target each launch was aimed at without re-running
    the strategy logic.
    """
    cfg = cfg or _DEFAULT_CONFIG
    return _decide_with_decisions(obs, cfg)


def _decide(obs: Any, cfg: HeuristicConfig) -> list[list[float | int]]:
    moves, _ = _decide_with_decisions(obs, cfg)
    return moves


def _decide_with_decisions(
    obs: Any, cfg: HeuristicConfig
) -> tuple[list[list[float | int]], list[LaunchDecision]]:
    view = ObservationView.from_raw(obs)
    if not view.my_planets:
        return [], []

    world = WorldModel.from_observation(view, horizon=cfg.sim_horizon)

    moves: list[list[float | int]] = []
    decisions: list[LaunchDecision] = []
    target_planets = [p for p in view.planets if p.owner != view.player]

    for src in view.my_planets:
        available = int(src.ships)
        if available < cfg.min_launch:
            continue

        # Sort targets by distance ascending — nearest-first sniper
        sorted_targets = sorted(
            target_planets, key=lambda t: dist(src.x, src.y, t.x, t.y)
        )

        for target in sorted_targets:
            result = _try_launch(src, target, view, world, cfg, available)
            if result is not None:
                angle, ships, eta = result
                moves.append([src.id, float(angle), int(ships)])
                decisions.append(
                    LaunchDecision(
                        src_id=src.id,
                        target_id=target.id,
                        angle=float(angle),
                        ships=int(ships),
                        eta=int(eta),
                        src_ships_pre_launch=int(src.ships),
                        target_ships_at_launch=int(target.ships),
                        target_owner=int(target.owner),
                        target_x=float(target.x),
                        target_y=float(target.y),
                        target_radius=float(target.radius),
                        target_is_static=is_static_planet(target.x, target.y, target.radius),
                        target_is_comet=view.is_comet(target.id),
                    )
                )
                break

    return moves, decisions


def _try_launch(
    src: Planet,
    target: Planet,
    view: ObservationView,
    world: WorldModel,
    cfg: HeuristicConfig,
    available: int,
) -> tuple[float, int, int] | None:
    """Plan one launch from src to target. Returns (angle, ships, eta) or None.

    Aiming strategy depends on target type:
    - **Static target**: aim straight at current position (target doesn't move).
    - **Orbiting planet or comet**: use ``aim_with_prediction`` to compute an
      intercept point. If the intercept solver returns None (e.g., predicted
      position is sun-blocked), SKIP this target — do NOT fall back to
      current-position aim, because that guarantees a miss.
    """
    target_is_moving = (not is_static_planet(target.x, target.y, target.radius)) or view.is_comet(target.id)

    # Initial ship estimate (sniper rule: target.ships + 1)
    ships_send = max(int(target.ships) + 1, cfg.min_launch)
    if ships_send > available:
        return None

    if target_is_moving:
        # Use the intercept solver
        initial = view.initial_by_id(target.id)
        comet_path = world.comet_paths.get(target.id) if view.is_comet(target.id) else None
        comet_idx = world.comet_path_indices.get(target.id, 0) if view.is_comet(target.id) else 0
        intercept = aim_with_prediction(
            src=src,
            target=target,
            ships=ships_send,
            initial=initial,
            angular_velocity=view.angular_velocity,
            comet_path=comet_path,
            comet_path_index=comet_idx,
        )
        if intercept is None:
            return None  # SKIP — current-position aim would just miss
        angle, eta, _predicted_xy = intercept
    else:
        # Static target — current-position aim
        launch = safe_angle_and_distance(
            src.x, src.y, src.radius,
            target.x, target.y, target.radius,
        )
        if launch is None:
            return None
        # ETA at this fleet size (size affects speed)
        probe = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
        if probe is None:
            return None
        angle, eta = probe

    if eta > cfg.route_search_horizon:
        return None

    # WorldModel cross-check: how many ships do we ACTUALLY need at arrival?
    need = world.min_ships_to_own_by(
        target_id=target.id,
        eval_turn=eta,
        attacker_owner=view.player,
        arrival_turn=eta,
    )
    if need is None or need <= 0:
        return None
    # Use the larger of (sniper rule, WorldModel forecast + buffer)
    ships_send = max(ships_send, int(need) + cfg.safety_margin)
    if ships_send > available:
        return None

    # If the fleet size grew, recompute angle/eta for self-consistency.
    # For moving targets we recompute via intercept; for static, simple ETA.
    if target_is_moving:
        intercept2 = aim_with_prediction(
            src=src, target=target, ships=ships_send,
            initial=view.initial_by_id(target.id),
            angular_velocity=view.angular_velocity,
            comet_path=world.comet_paths.get(target.id) if view.is_comet(target.id) else None,
            comet_path_index=world.comet_path_indices.get(target.id, 0) if view.is_comet(target.id) else 0,
        )
        if intercept2 is None:
            return None
        angle, eta, _ = intercept2
    else:
        probe2 = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
        if probe2 is None:
            return None
        angle, eta = probe2

    # Path-clearance check: walk the trajectory turn-by-turn, predict other planets'
    # positions, and reject if any non-target enemy/neutral planet would sweep the fleet.
    # Skip own-planet collisions (those reinforce our garrison — not a loss).
    obstruction = path_collision_predicted(
        src=src, target=target, angle=angle, ships=ships_send, eta=eta,
        view=view, skip_own=True,
    )
    if obstruction is not None:
        return None  # SKIP — fleet would be intercepted by `obstruction` mid-flight

    return angle, ships_send, eta
