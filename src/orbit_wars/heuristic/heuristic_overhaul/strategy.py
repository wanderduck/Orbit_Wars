"""Top-level v2 heuristic agent   Advanced Utility-Driven Mission Planner."""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from orbit_wars.geometry import dist, is_static_planet, safe_angle_and_distance
from orbit_wars.state import ObservationView, Planet
from orbit_wars.world import WorldModel, aim_with_prediction, estimate_fleet_eta, path_collision_predicted
from .config import HeuristicConfig

__all__ = ["LaunchDecision", "Threat", "agent", "decide_with_decisions"]


@dataclass(frozen=True, slots=True)
class LaunchDecision:
    src_id: int; target_id: int; angle: float; ships: int; eta: int
    src_ships_pre_launch: int; target_ships_at_launch: int; target_owner: int
    target_x: float; target_y: float; target_radius: float
    target_is_static: bool; target_is_comet: bool
    mission: str = "capture"


@dataclass(frozen=True, slots=True)
class Threat:
    planet_id: int; fall_turn: int; incoming_owner: int


_DEFAULT_CONFIG = HeuristicConfig.default()
EPISODE_STEPS: int = 500


def agent(obs: Any, config: HeuristicConfig | None = None) -> list[list[float | int]]:
    cfg = config if isinstance(config, HeuristicConfig) else _DEFAULT_CONFIG
    try:
        return _decide(obs, cfg)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return []


def decide_with_decisions(
    obs: Any, config: HeuristicConfig | None = None,
) -> tuple[list[list[float | int]], list[LaunchDecision]]:
    cfg = config if isinstance(config, HeuristicConfig) else _DEFAULT_CONFIG
    return _decide_with_decisions(obs, cfg)


def _decide(obs: Any, cfg: HeuristicConfig) -> list[list[float | int]]:
    moves, _ = _decide_with_decisions(obs, cfg)
    return moves


def _get_domination(view: ObservationView, remaining_steps: int) -> float:
    # INTELLIGENCE BOOST: Account for planet production in domination tracking!
    horizon = min(remaining_steps, 50)
    my_ships = sum(p.ships + getattr(p, 'production', 0) * horizon for p in view.my_planets) + \
               sum(f.ships for f in view.fleets if f.owner == view.player)

    enemy_ships_by_id = {}
    for p in view.planets:
        if p.owner not in (-1, view.player):
            val = p.ships + getattr(p, 'production', 0) * horizon
            enemy_ships_by_id[p.owner] = enemy_ships_by_id.get(p.owner, 0) + val

    for f in view.fleets:
        if f.owner not in (-1, view.player):
            enemy_ships_by_id[f.owner] = enemy_ships_by_id.get(f.owner, 0) + f.ships

    max_enemy_ships = max(enemy_ships_by_id.values()) if enemy_ships_by_id else 0
    total = max(1.0, float(my_ships + max_enemy_ships))
    return float((my_ships - max_enemy_ships) / total)


def get_exposed_planets(view: ObservationView, cfg: HeuristicConfig) -> set[int]:
    """Identifies enemy planets that have exhausted their garrison by launching a major outbound fleet."""
    exposed = set()
    enemy_planets = [p for p in view.planets if p.owner not in (-1, view.player)]
    for planet in enemy_planets:
        outbound = sum(
            int(f.ships)
            for f in view.fleets
            if (
                f.owner == planet.owner
                and getattr(f, "from_planet_id", -1) == planet.id
                and f.ships >= cfg.exposed_planet_min_fleet_ships
            )
        )
        if outbound >= cfg.exposed_planet_min_outbound and outbound >= planet.ships:
            exposed.add(planet.id)
    return exposed


def find_threats(view: ObservationView, world: WorldModel, cfg: HeuristicConfig) -> list[Threat]:
    threats: list[Threat] = []
    if not cfg.reinforce_enabled:
        return threats

    # INTELLIGENCE BOOST: Track neutral captures that fall immediately after taking them
    for planet in view.planets:
        timeline = world.base_timeline.get(planet.id)
        if not timeline: continue
        we_own = (planet.owner == view.player)
        for t in range(1, timeline.horizon + 1):
            if timeline.owner_at[t] == view.player:
                we_own = True
            elif we_own and timeline.owner_at[t] != view.player and timeline.owner_at[t] != -1:
                threats.append(Threat(planet_id=planet.id, fall_turn=t, incoming_owner=timeline.owner_at[t]))
                break
    return threats


def _score_candidate(
    src: Planet, target: Planet, ships: int, eta: int, mission: str,
    view: ObservationView, cfg: HeuristicConfig, remaining_steps: int, domination: float,
    min_my_dist: float, min_enemy_dist: float, exposed_planets: set[int]
) -> float:
    is_static = is_static_planet(target.x, target.y, target.radius)
    is_comet = view.is_comet(target.id)
    is_neutral = target.owner == -1
    is_hostile = not is_neutral and target.owner != view.player
    turn = view.step
    is_early = turn <= cfg.early_turn_limit
    is_opening = turn <= cfg.opening_turn_limit
    is_total_war = remaining_steps <= cfg.total_war_remaining_turns

    base_val = float(target.radius) if float(target.radius) > 0.0 else 1.0
    mult = 1.0

    if mission in ("reinforce", "redistribute"):
        mult *= cfg.reinforce_value_mult
        cost_weight = cfg.reinforce_cost_turn_weight
        # INTELLIGENCE BOOST: Parameterized multiplier applied
        if min_enemy_dist <= min_my_dist + cfg.defense_frontier_distance:
            mult *= cfg.defense_frontier_score_mult
    else:
        # INTELLIGENCE BOOST: Parameterized multiplier applied
        if getattr(target, 'ships', 0) <= cfg.snipe_ships_threshold:
            mult *= cfg.snipe_score_mult

        if is_neutral:
            cost_weight = cfg.snipe_cost_turn_weight if getattr(target, 'ships', 0) <= cfg.snipe_ships_threshold else cfg.attack_cost_turn_weight

            if is_static:
                mult *= cfg.static_neutral_value_mult
                if is_early:
                    mult *= cfg.early_static_neutral_score_mult
            else:
                if is_early:
                    mult *= cfg.early_neutral_value_mult
                if is_opening:
                    mult *= cfg.rotating_opening_value_mult

            # Evaluated securely with O(1) distances
            if min_my_dist < min_enemy_dist - cfg.safe_contested_neutral_margin:
                mult *= cfg.safe_neutral_value_mult
            elif min_enemy_dist < min_my_dist + cfg.safe_contested_neutral_margin:
                mult *= cfg.contested_neutral_value_mult

        elif is_hostile:
            cost_weight = cfg.snipe_cost_turn_weight if getattr(target, 'ships', 0) <= cfg.snipe_ships_threshold else cfg.attack_cost_turn_weight
            mult *= cfg.hostile_target_value_mult
            if is_static:
                mult *= cfg.static_hostile_value_mult
                mult *= cfg.static_target_score_mult
            elif is_opening:
                mult *= cfg.opening_hostile_target_value_mult

            if getattr(target, 'ships', 0) < cfg.weak_enemy_threshold:
                base_val += cfg.elimination_bonus

            if getattr(target, 'ships', 0) == 0:
                mult *= cfg.crash_exploit_score_mult

    if domination < cfg.behind_domination:
        mult *= (1.0 - cfg.behind_attack_margin_penalty)
    elif domination > cfg.ahead_domination:
        mult *= (1.0 + cfg.ahead_attack_margin_bonus)

    if remaining_steps <= cfg.late_remaining_turns:
        base_val += cfg.late_immediate_ship_value * getattr(target, 'ships', 0.0)

    if domination > cfg.finishing_domination and is_total_war:
        mult *= cfg.finishing_prod_ratio

    if is_comet:
        mult *= cfg.comet_value_mult

    if is_hostile and target.id in exposed_planets:
        mult *= cfg.exposed_planet_value_mult

    if ships > cfg.swarm_min_fleet_size and getattr(target, 'ships', 0) < ships * cfg.swarm_overkill_ratio:
        mult *= cfg.swarm_score_mult

    cost = float(ships) + float(eta) * cost_weight + 1.0
    return float((base_val * mult) / cost)


def _try_launch(
    src: Planet, target: Planet, view: ObservationView, world: WorldModel,
    cfg: HeuristicConfig, available: int, domination: float,
    need_cache: dict[tuple[int, int], int | None], exposed_planets: set[int]
) -> tuple[float, int, int] | None:
    target_is_moving = (not is_static_planet(target.x, target.y, target.radius)) or view.is_comet(target.id)

    ships_send = max(int(getattr(target, 'ships', 0)) + 1, cfg.min_launch)
    if ships_send > available: return None

    # INTELLIGENCE BOOST: Convergence loop to fix the Fleet Speed / ETA Catch-22 bug
    angle, eta = 0.0, 0
    converged = False
    for _ in range(3):
        if target_is_moving:
            intercept = aim_with_prediction(
                src=src, target=target, ships=ships_send, initial=view.initial_by_id(target.id),
                angular_velocity=view.angular_velocity,
                comet_path=world.comet_paths.get(target.id) if view.is_comet(target.id) else None,
                comet_path_index=world.comet_path_indices.get(target.id, 0) if view.is_comet(target.id) else 0,
            )
            if not intercept: return None
            angle, eta, _ = intercept
        else:
            probe = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
            if not probe: return None
            angle, eta = probe

        if eta > cfg.route_search_horizon:
            return None

        # COMPUTE BOOST: O(1) Timeline Simulation Memoization
        cache_key = (target.id, eta)
        if cache_key not in need_cache:
            need_cache[cache_key] = world.min_ships_to_own_by(
                target_id=target.id, eval_turn=eta, attacker_owner=view.player, arrival_turn=eta
            )
        need = need_cache[cache_key]

        if not need or need <= 0: return None

        margin = cfg.safety_margin
        if domination < cfg.behind_domination: margin = max(0, margin - 1)
        elif domination > cfg.ahead_domination: margin += 1

        if target.owner not in (-1, view.player) and target.id in exposed_planets:
            margin = max(0, margin - cfg.exposed_planet_margin_relief)

        required_ships = max(ships_send, int(need) + margin)

        if required_ships > available: return None
        if required_ships == ships_send:
            converged = True
            break

        ships_send = required_ships

    if not converged:
        return None

    if path_collision_predicted(
        src=src, target=target, angle=angle, ships=ships_send, eta=eta,
        view=view, comet_paths=world.comet_paths, comet_path_indices=world.comet_path_indices, skip_own=True,
    ):
        return None

    return angle, ships_send, eta


def _plan_missions_unified(
    view: ObservationView, world: WorldModel, cfg: HeuristicConfig,
    target_planets: list[Planet], threats: list[Threat], remaining_steps: int, domination: float
) -> tuple[list[list[float | int]], list[LaunchDecision]]:
    candidates = []
    planets_by_id = {p.id: p for p in view.planets}
    is_total_war = remaining_steps <= cfg.total_war_remaining_turns

    enemy_planets = [p for p in view.planets if p.owner not in (-1, view.player)]
    target_min_my_dist = {}
    target_min_enemy_dist = {}

    all_targets = set(target_planets)
    for threat in threats:
        tgt = planets_by_id.get(threat.planet_id)
        if tgt is not None:
            all_targets.add(tgt)

    for tgt in all_targets:
        my_dists = [dist(tgt.x, tgt.y, p.x, p.y) for p in view.my_planets]
        en_dists = [dist(tgt.x, tgt.y, p.x, p.y) for p in enemy_planets]
        target_min_my_dist[tgt.id] = min(my_dists) if my_dists else 1e9
        target_min_enemy_dist[tgt.id] = min(en_dists) if en_dists else 1e9

    exposed_planets = get_exposed_planets(view, cfg)
    need_cache: dict[tuple[int, int], int | None] = {}
    defense_cache: dict[tuple[int, int], int | None] = {}

    # 1. Build Defense Candidates
    for threat in threats:
        target = planets_by_id.get(threat.planet_id)
        if target is None or target.owner != view.player: continue
        hold_until = min(world.horizon, threat.fall_turn + cfg.reinforce_hold_lookahead)

        for src in view.my_planets:
            if src.id == target.id: continue

            available = int(src.ships) - (0 if is_total_war else cfg.defense_buffer)
            cap = int(int(src.ships) * cfg.reinforce_max_source_fraction)
            usable = min(available, cap)
            if usable < cfg.min_launch: continue

            probe = estimate_fleet_eta(src, (target.x, target.y), target.radius, usable)
            if not probe or probe[1] > threat.fall_turn: continue

            d_key = (target.id, probe[1])
            if d_key not in defense_cache:
                defense_cache[d_key] = world.reinforcement_needed_to_hold_until(
                    target_id=target.id, hold_until=hold_until, arrival_turn=probe[1], defender=view.player,
                )
            need = defense_cache[d_key]

            if not need or need <= 0: continue
            ships_send = max(cfg.min_launch, int(need) + cfg.reinforce_safety_margin)
            ships_send = min(ships_send, available, cap)

            if ships_send < cfg.min_launch: continue

            probe2 = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
            if not probe2 or probe2[1] > threat.fall_turn or probe2[1] > remaining_steps: continue
            angle, eta = probe2

            score = _score_candidate(src, target, ships_send, eta, "reinforce", view, cfg, remaining_steps, domination, target_min_my_dist.get(target.id, 0), target_min_enemy_dist.get(target.id, 0), exposed_planets)
            if score > 0:
                if not path_collision_predicted(
                    src=src, target=target, angle=angle, ships=ships_send, eta=eta,
                    view=view, comet_paths=world.comet_paths, comet_path_indices=world.comet_path_indices, skip_own=True,
                ):
                    candidates.append((src, target, angle, ships_send, eta, score, "reinforce"))

    # 2. Build Macro Backline Redistribution Candidates ("Dead Backline" Fix)
    for src in view.my_planets:
        # Only mobilize planets far from the frontline using configurable boundaries
        if target_min_enemy_dist.get(src.id, 0) < cfg.backline_safe_distance: continue

        available = int(src.ships) - cfg.home_reserve
        if available < cfg.min_launch * 2: continue

        for target in view.my_planets:
            if src.id == target.id: continue

            dist_diff = target_min_enemy_dist.get(src.id, 0) - target_min_enemy_dist.get(target.id, 0)
            if dist_diff < cfg.redistribute_min_dist_diff: continue

            ships_send = min(int(available * 0.8), available)
            if ships_send < cfg.min_launch: continue

            probe = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
            if not probe: continue
            angle, eta = probe

            if eta > remaining_steps or eta > cfg.route_search_horizon: continue

            score = _score_candidate(src, target, ships_send, eta, "redistribute", view, cfg, remaining_steps, domination, target_min_my_dist.get(target.id, 0), target_min_enemy_dist.get(target.id, 0), exposed_planets)
            score *= (dist_diff / cfg.redistribute_scale_factor)

            if score > 0:
                if not path_collision_predicted(
                    src=src, target=target, angle=angle, ships=ships_send, eta=eta,
                    view=view, comet_paths=world.comet_paths, comet_path_indices=world.comet_path_indices, skip_own=True,
                ):
                    candidates.append((src, target, angle, ships_send, eta, score, "redistribute"))

    # 3. Build Offense Candidates
    for src in view.my_planets:
        available = int(src.ships) - (0 if is_total_war else cfg.home_reserve)
        if available < cfg.min_launch: continue

        for target in target_planets:
            result = _try_launch(src, target, view, world, cfg, available, domination, need_cache, exposed_planets)
            if not result: continue
            angle, ships, eta = result

            score = _score_candidate(src, target, ships, eta, "capture", view, cfg, remaining_steps, domination, target_min_my_dist.get(target.id, 0), target_min_enemy_dist.get(target.id, 0), exposed_planets)
            if score > 0:
                candidates.append((src, target, angle, ships, eta, score, "capture"))

    moves, decisions = [], []
    if not candidates: return moves, decisions

    # 4. Iterative Hungarian Dispatch (Solves the 1-to-1 Bottleneck)
    assigned_tgts = set()
    available_ships = {p.id: int(p.ships) - (0 if is_total_war else cfg.home_reserve) for p in view.my_planets}

    if cfg.use_hungarian_offense:
        while candidates:
            # Filter candidates dynamically based on remaining ships after assignments
            valid_candidates = [
                c for c in candidates
                if (c[1].id, c[6]) not in assigned_tgts
                and c[3] <= available_ships.get(c[0].id, 0)
            ]
            if not valid_candidates:
                break

            src_ids = sorted({c[0].id for c in valid_candidates})
            tgt_keys = sorted({(c[1].id, c[6]) for c in valid_candidates})

            src_idx = {sid: i for i, sid in enumerate(src_ids)}
            tgt_idx = {tkey: j for j, tkey in enumerate(tgt_keys)}

            score_matrix = np.zeros((len(src_ids), len(tgt_keys)), dtype=np.float64)
            detail = {}

            for c in valid_candidates:
                src, target, angle, ships, eta, score, mission = c
                i, j = src_idx[src.id], tgt_idx[(target.id, mission)]
                if score > score_matrix[i, j]:
                    score_matrix[i, j] = score
                    detail[(i, j)] = c

            row_ind, col_ind = linear_sum_assignment(score_matrix, maximize=True)
            assignments_made = 0

            for i, j in zip(row_ind, col_ind, strict=False):
                if score_matrix[i, j] > 0.0:
                    src, target, angle, ships, eta, score, mission = detail[(i, j)]
                    moves.append([src.id, float(angle), int(ships)])
                    decisions.append(LaunchDecision(
                        src_id=src.id, target_id=target.id, angle=float(angle), ships=int(ships), eta=int(eta),
                        src_ships_pre_launch=int(src.ships), target_ships_at_launch=int(target.ships), target_owner=int(target.owner),
                        target_x=float(target.x), target_y=float(target.y), target_radius=float(target.radius),
                        target_is_static=is_static_planet(target.x, target.y, target.radius),
                        target_is_comet=view.is_comet(target.id), mission=mission,
                    ))
                    available_ships[src.id] -= int(ships)
                    assigned_tgts.add((target.id, mission))
                    assignments_made += 1

            if assignments_made == 0:
                break
    else:
        # Improved Greedy Multi-Dispatch allowing multiple launches
        candidates.sort(key=lambda c: c[5], reverse=True)
        for c in candidates:
            src, target, angle, ships, eta, score, mission = c
            if (target.id, mission) in assigned_tgts: continue

            if ships <= available_ships.get(src.id, 0):
                moves.append([src.id, float(angle), int(ships)])
                decisions.append(LaunchDecision(
                    src_id=src.id, target_id=target.id, angle=float(angle), ships=int(ships), eta=int(eta),
                    src_ships_pre_launch=int(src.ships), target_ships_at_launch=int(target.ships), target_owner=int(target.owner),
                    target_x=float(target.x), target_y=float(target.y), target_radius=float(target.radius),
                    target_is_static=is_static_planet(target.x, target.y, target.radius),
                    target_is_comet=view.is_comet(target.id), mission=mission,
                ))
                available_ships[src.id] -= int(ships)
                assigned_tgts.add((target.id, mission))

    return moves, decisions


def _decide_with_decisions(obs: Any, cfg: HeuristicConfig) -> tuple[list[list[float | int]], list[LaunchDecision]]:
    view = ObservationView.from_raw(obs)
    if not view.my_planets:
        return [], []

    world = WorldModel.from_observation(view, horizon=cfg.sim_horizon)
    remaining_steps = max(0, EPISODE_STEPS - view.step)
    domination = _get_domination(view, remaining_steps)

    target_planets = [p for p in view.planets if p.owner != view.player]
    threats = find_threats(view, world, cfg)

    return _plan_missions_unified(view, world, cfg, target_planets, threats, remaining_steps, domination)