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

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..geometry import dist, is_static_planet, safe_angle_and_distance
from ..state import ObservationView, Planet
from ..world import WorldModel, aim_with_prediction, estimate_fleet_eta, path_collision_predicted
from .config import HeuristicConfig

__all__ = ["LaunchDecision", "Threat", "agent", "decide_with_decisions"]


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
    mission: str = "capture"  # "capture" or "reinforce"


@dataclass(frozen=True, slots=True)
class Threat:
    """An owned planet projected to flip ownership during the WorldModel horizon."""

    planet_id: int
    fall_turn: int
    incoming_owner: int


_DEFAULT_CONFIG = HeuristicConfig.default()

# Total episode length (per kaggle_environments env config: episodeSteps=500).
EPISODE_STEPS: int = 500


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
    config: HeuristicConfig | None = None,
) -> tuple[list[list[float | int]], list[LaunchDecision]]:
    """Same algorithm as ``agent``/``_decide``, but also returns per-launch metadata.

    Used by the diagnostic harness in ``tools/diagnostic.py``. Public so external
    tooling can introspect what target each launch was aimed at without re-running
    the strategy logic.

    The ``config`` guard is the same isinstance pattern used by ``agent`` — see
    that function's docstring for why ``cfg = config or DEFAULT`` is unsafe.
    """
    if isinstance(config, HeuristicConfig):
        cfg = config
    else:
        cfg = _DEFAULT_CONFIG
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
    # `view.step` is 1-indexed (kaggle_environments populates obs.step for the
    # current turn). remaining_steps = turns left in the episode after this one.
    remaining_steps = max(0, EPISODE_STEPS - view.step)

    moves: list[list[float | int]] = []
    decisions: list[LaunchDecision] = []

    # ----- Defense phase -----
    # Identify owned planets the WorldModel forecasts will flip; reinforce from
    # the nearest viable source. Defense reservations subtract from the offense
    # budget per source via `used_ships`.
    threats = find_threats(view, world, cfg)
    defense_moves, defense_decisions, used_ships = plan_defense(
        view, world, threats, cfg, remaining_steps=remaining_steps,
    )
    moves.extend(defense_moves)
    decisions.extend(defense_decisions)

    # ----- Offense phase: Hungarian one-to-one optimal assignment -----
    # Build the candidate pool: every viable (src, target) pair that passes
    # _try_launch (sun-safe, affordable, path-clear, target reachable). Then
    # solve a one-to-one matching that minimizes total cost. This avoids the
    # greedy failure mode where multiple sources race to the same nearest
    # target while leaving other targets uncontested.
    target_planets = [p for p in view.planets if p.owner != view.player]
    offense_moves, offense_decisions = _plan_offense_hungarian(
        view, world, cfg, target_planets, used_ships,
        remaining_steps=remaining_steps,
    )
    moves.extend(offense_moves)
    decisions.extend(offense_decisions)

    return moves, decisions


def _plan_offense_hungarian(
    view: ObservationView,
    world: WorldModel,
    cfg: HeuristicConfig,
    target_planets: list[Planet],
    used_ships: dict[int, int],
    *,
    remaining_steps: int,
) -> tuple[list[list[float | int]], list[LaunchDecision]]:
    """Build candidate launches and solve the (src → target) assignment via Hungarian.

    Cost = ships_needed + eta * 0.5 (penalize both expensive and slow captures).
    Sources with no viable target produce no launch. Each src matched to at most
    one target; each target matched to at most one src (per turn).
    """
    # Step 1: collect viable candidates (skipping launches that arrive after
    # episode end — wasted ships).
    candidates: list[tuple[Planet, Planet, float, int, int]] = []
    for src in view.my_planets:
        committed = used_ships.get(src.id, 0)
        available = int(src.ships) - committed
        if available < cfg.min_launch:
            continue
        for target in target_planets:
            result = _try_launch(src, target, view, world, cfg, available)
            if result is None:
                continue
            angle, ships, eta = result
            if eta > remaining_steps:
                continue  # launch would arrive after episode ends
            candidates.append((src, target, angle, ships, eta))

    if not candidates:
        return [], []

    # Step 2: build cost matrix
    src_ids = sorted({c[0].id for c in candidates})
    tgt_ids = sorted({c[1].id for c in candidates})
    src_idx = {sid: i for i, sid in enumerate(src_ids)}
    tgt_idx = {tid: j for j, tid in enumerate(tgt_ids)}

    INF = 1e9
    cost = np.full((len(src_ids), len(tgt_ids)), INF, dtype=np.float64)
    detail: dict[tuple[int, int], tuple[float, int, int, Planet, Planet]] = {}
    for src, target, angle, ships, eta in candidates:
        i, j = src_idx[src.id], tgt_idx[target.id]
        c = float(ships) + 0.5 * float(eta)
        if c < cost[i, j]:
            cost[i, j] = c
            detail[(i, j)] = (angle, ships, eta, src, target)

    # Step 3: prune all-INF rows BEFORE solving. Otherwise `linear_sum_assignment`
    # picks cells in those rows (it always assigns min(M,N) pairs), and an INF cell
    # can "consume" a target slot that another viable source would have used.
    viable_rows = [i for i in range(cost.shape[0]) if np.any(cost[i] < INF)]
    if not viable_rows:
        return [], []
    cost_pruned = cost[viable_rows]

    row_ind, col_ind = linear_sum_assignment(cost_pruned)

    # Step 4: build moves/decisions from chosen cells.
    # row_ind indexes into cost_pruned; map back to the original via viable_rows.
    moves: list[list[float | int]] = []
    decisions: list[LaunchDecision] = []
    for pruned_i, j in zip(row_ind, col_ind, strict=False):
        i = viable_rows[pruned_i]
        if cost[i, j] >= INF:
            continue  # this source has no viable target
        angle, ships, eta, src, target = detail[(i, j)]
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
                mission="capture",
            )
        )
        used_ships[src.id] = used_ships.get(src.id, 0) + ships
    return moves, decisions


def find_threats(
    view: ObservationView,
    world: WorldModel,
    cfg: HeuristicConfig,
) -> list[Threat]:
    """Identify owned planets forecast to flip ownership during the WorldModel horizon.

    Walks ``WorldModel.base_timeline`` for each owned planet and returns the
    earliest turn at which ``owner_at[t] != view.player``. WorldModel timelines
    already include in-flight enemy fleets, target production, and same-turn
    combat resolution, so this catches all threats the model can see at obs time.
    """
    threats: list[Threat] = []
    if not cfg.reinforce_enabled:
        return threats
    for planet in view.my_planets:
        timeline = world.base_timeline.get(planet.id)
        if timeline is None:
            continue
        for t in range(1, timeline.horizon + 1):
            if timeline.owner_at[t] != view.player:
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
    cfg: HeuristicConfig,
    *,
    remaining_steps: int = EPISODE_STEPS,
) -> tuple[list[list[float | int]], list[LaunchDecision], dict[int, int]]:
    """Plan reinforcement launches for threats; returns (moves, decisions, used_ships).

    For each threat (sorted urgency-first), find the nearest owned source that:
    1. Has enough ships available to ship the reinforcement (capped by
       ``reinforce_max_source_fraction`` of source's garrison).
    2. Can reach the target before ``fall_turn``.
    3. Has a sun-safe, path-clear trajectory.

    Defense ships are tracked in ``used_ships`` so the offense phase doesn't
    double-spend them.
    """
    moves: list[list[float | int]] = []
    decisions: list[LaunchDecision] = []
    used_ships: dict[int, int] = {}

    if not cfg.reinforce_enabled or not threats:
        return moves, decisions, used_ships

    sorted_threats = sorted(threats, key=lambda t: t.fall_turn)
    planets_by_id = {p.id: p for p in view.planets}

    for threat in sorted_threats:
        target = planets_by_id.get(threat.planet_id)
        if target is None or target.owner != view.player:
            continue
        if threat.fall_turn > cfg.reinforce_max_travel_turns + 5:
            continue  # too far ahead — wait for firmer signal

        hold_until = min(world.horizon, threat.fall_turn + cfg.reinforce_hold_lookahead)

        # Collect candidate sources sorted by distance to threatened planet.
        candidates = []
        for src in view.my_planets:
            if src.id == target.id:
                continue
            committed = used_ships.get(src.id, 0)
            available = int(src.ships) - committed
            cap = int(int(src.ships) * cfg.reinforce_max_source_fraction)
            usable = min(available, cap)
            if usable < cfg.min_launch:
                continue
            candidates.append(src)
        candidates.sort(key=lambda s: dist(s.x, s.y, target.x, target.y))

        for src in candidates:
            committed = used_ships.get(src.id, 0)
            available = int(src.ships) - committed
            cap = int(int(src.ships) * cfg.reinforce_max_source_fraction)
            usable = min(available, cap)
            if usable < cfg.min_launch:
                continue

            # Compute ETA at a probe size first; reject if can't arrive in time.
            probe = estimate_fleet_eta(src, (target.x, target.y), target.radius, usable)
            if probe is None:
                continue
            angle, eta = probe
            # Must arrive STRICTLY before the planet falls (== same turn doesn't help —
            # production already triggered for the prior owner; combat resolves with
            # the enemy's projected ships at fall_turn).
            if eta > threat.fall_turn:
                continue

            # Compute reinforcement need with the ACTUAL arrival turn (NOT 1) — fleet
            # arriving at turn `eta` doesn't help with combat that resolves at turn < eta.
            # `reinforcement_needed_to_hold_until` simulates a defender arriving at
            # `arrival_turn`; passing eta here gives an honest estimate.
            need = world.reinforcement_needed_to_hold_until(
                target_id=target.id,
                hold_until=hold_until,
                arrival_turn=eta,
                defender=view.player,
            )
            if need is None or need <= 0:
                continue

            ships_send = max(cfg.min_launch, int(need) + cfg.reinforce_safety_margin)
            ships_send = min(ships_send, available, cap)
            if ships_send < cfg.min_launch:
                continue

            # Re-probe ETA with the actual fleet size (size affects speed)
            probe2 = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
            if probe2 is None:
                continue
            angle, eta = probe2
            if eta > threat.fall_turn:
                continue
            if eta > remaining_steps:
                continue  # arrives after episode ends

            # Path-clearance: don't lose the reinforcement to an interceptor.
            # Pass comet paths so the check is comet-aware.
            obstruction = path_collision_predicted(
                src=src, target=target, angle=angle, ships=ships_send, eta=eta,
                view=view,
                comet_paths=world.comet_paths,
                comet_path_indices=world.comet_path_indices,
                skip_own=True,
            )
            if obstruction is not None:
                continue

            moves.append([src.id, float(angle), int(ships_send)])
            decisions.append(
                LaunchDecision(
                    src_id=src.id,
                    target_id=target.id,
                    angle=float(angle),
                    ships=int(ships_send),
                    eta=int(eta),
                    src_ships_pre_launch=int(src.ships),
                    target_ships_at_launch=int(target.ships),
                    target_owner=int(target.owner),
                    target_x=float(target.x),
                    target_y=float(target.y),
                    target_radius=float(target.radius),
                    target_is_static=is_static_planet(target.x, target.y, target.radius),
                    target_is_comet=view.is_comet(target.id),
                    mission="reinforce",
                )
            )
            used_ships[src.id] = used_ships.get(src.id, 0) + ships_send
            break  # one defender per threat

    return moves, decisions, used_ships


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
    # Pass comet paths so comet movement is predicted correctly (not as orbital rotation).
    # Skip own-planet collisions (those reinforce our garrison — not a loss).
    obstruction = path_collision_predicted(
        src=src, target=target, angle=angle, ships=ships_send, eta=eta,
        view=view,
        comet_paths=world.comet_paths,
        comet_path_indices=world.comet_path_indices,
        skip_own=True,
    )
    if obstruction is not None:
        return None  # SKIP — fleet would be intercepted by `obstruction` mid-flight

    return angle, ships_send, eta
