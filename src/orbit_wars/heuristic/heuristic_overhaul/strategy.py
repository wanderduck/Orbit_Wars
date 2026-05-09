"""Top-level v2 heuristic agent — Advanced Utility-Driven Mission Planner."""

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
	src_id: int;
	target_id: int;
	angle: float;
	ships: int;
	eta: int
	src_ships_pre_launch: int;
	target_ships_at_launch: int;
	target_owner: int
	target_x: float;
	target_y: float;
	target_radius: float
	target_is_static: bool;
	target_is_comet: bool
	mission: str = "capture"


@dataclass(frozen=True, slots=True)
class Threat:
	planet_id: int;
	fall_turn: int;
	incoming_owner: int


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


def _get_domination(view: ObservationView) -> float:
	my_ships = sum(p.ships for p in view.my_planets) + sum(f.ships for f in view.fleets if f.owner == view.player)
	enemy_ships_by_id = {}
	for p in view.planets:
		if p.owner not in (-1, view.player):
			enemy_ships_by_id[p.owner] = enemy_ships_by_id.get(p.owner, 0) + p.ships
	for f in view.fleets:
		if f.owner not in (-1, view.player):
			enemy_ships_by_id[f.owner] = enemy_ships_by_id.get(f.owner, 0) + f.ships

	max_enemy_ships = max(enemy_ships_by_id.values()) if enemy_ships_by_id else 0
	total = max(1.0, float(my_ships + max_enemy_ships))
	return float((my_ships - max_enemy_ships) / total)


def find_threats(view: ObservationView, world: WorldModel, cfg: HeuristicConfig) -> list[Threat]:
	threats: list[Threat] = []
	if not cfg.reinforce_enabled:
		return threats
	for planet in view.my_planets:
		timeline = world.base_timeline.get(planet.id)
		if not timeline: continue
		for t in range(1, timeline.horizon + 1):
			if timeline.owner_at[t] != view.player:
				threats.append(Threat(planet_id=planet.id, fall_turn=t, incoming_owner=timeline.owner_at[t]))
				break
	return threats


def _score_candidate(
		src: Planet, target: Planet, ships: int, eta: int, mission: str,
		view: ObservationView, cfg: HeuristicConfig, remaining_steps: int, domination: float
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

	if mission == "reinforce":
		mult *= cfg.reinforce_value_mult
		cost_weight = cfg.reinforce_cost_turn_weight
	else:
		if is_neutral:
			cost_weight = cfg.snipe_cost_turn_weight if target.ships <= 10 else cfg.attack_cost_turn_weight
			if is_static:
				mult *= cfg.static_neutral_value_mult
				if is_early: mult *= cfg.early_static_neutral_score_mult
			else:
				if is_early: mult *= cfg.early_neutral_value_mult
				if is_opening: mult *= cfg.rotating_opening_value_mult

			my_dists = [dist(target.x, target.y, p.x, p.y) for p in view.my_planets]
			enemy_planets = [p for p in view.planets if p.owner not in (-1, view.player)]
			enemy_dists = [dist(target.x, target.y, p.x, p.y) for p in enemy_planets]
			min_my_dist = min(my_dists) if my_dists else 1e9
			min_enemy_dist = min(enemy_dists) if enemy_dists else 1e9

			if min_my_dist < min_enemy_dist - 15:
				mult *= cfg.safe_neutral_value_mult
			elif min_enemy_dist < min_my_dist + 15:
				mult *= cfg.contested_neutral_value_mult

		elif is_hostile:
			cost_weight = cfg.snipe_cost_turn_weight if target.ships <= 10 else cfg.attack_cost_turn_weight
			mult *= cfg.hostile_target_value_mult

			if is_static:
				mult *= cfg.static_hostile_value_mult
				mult *= cfg.static_target_score_mult
			elif is_opening:
				mult *= cfg.opening_hostile_target_value_mult

			if getattr(target, 'ships', 0) < cfg.weak_enemy_threshold:
				base_val += cfg.elimination_bonus
			if target.ships == 0:
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
		if ships > 50 and getattr(target, 'ships', 0) < ships * 0.3:
			mult *= cfg.swarm_score_mult

	cost = float(ships) + float(eta) * cost_weight + 1.0
	return float((base_val * mult) / cost)


def _try_launch(
		src: Planet, target: Planet, view: ObservationView, world: WorldModel,
		cfg: HeuristicConfig, available: int, domination: float,
		) -> tuple[float, int, int] | None:
	target_is_moving = (not is_static_planet(target.x, target.y, target.radius)) or view.is_comet(target.id)
	ships_send = max(int(target.ships) + 1, cfg.min_launch)
	if ships_send > available: return None

	if target_is_moving:
		intercept = aim_with_prediction(
			src=src, target=target, ships=ships_send, initial=view.initial_by_id(target.id),
			angular_velocity=view.angular_velocity,
			comet_path=world.comet_paths.get(target.id) if view.is_comet(target.id) else None,
			comet_path_index=world.comet_path_indices.get(target.id, 0) if view.is_comet(target.id) else 0,
			)
		if not intercept: return None
		angle, eta, _predicted_xy = intercept
	else:
		launch = safe_angle_and_distance(src.x, src.y, src.radius, target.x, target.y, target.radius)
		if not launch: return None
		probe = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
		if not probe: return None
		angle, eta = probe

	if eta > cfg.route_search_horizon: return None

	need = world.min_ships_to_own_by(target_id=target.id, eval_turn=eta, attacker_owner=view.player, arrival_turn=eta)
	if not need or need <= 0: return None

	margin = cfg.safety_margin
	if domination < cfg.behind_domination:
		margin = max(0, margin - 1)
	elif domination > cfg.ahead_domination:
		margin += 1

	ships_send = max(ships_send, int(need) + margin)
	if ships_send > available: return None

	if target_is_moving:
		intercept2 = aim_with_prediction(
			src=src, target=target, ships=ships_send, initial=view.initial_by_id(target.id),
			angular_velocity=view.angular_velocity,
			comet_path=world.comet_paths.get(target.id) if view.is_comet(target.id) else None,
			comet_path_index=world.comet_path_indices.get(target.id, 0) if view.is_comet(target.id) else 0,
			)
		if not intercept2: return None
		angle, eta, _ = intercept2
	else:
		probe2 = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
		if not probe2: return None
		angle, eta = probe2

	if path_collision_predicted(
			src=src, target=target, angle=angle, ships=ships_send, eta=eta, view=view,
			comet_paths=world.comet_paths, comet_path_indices=world.comet_path_indices, skip_own=True,
			): return None

	return angle, ships_send, eta


def _plan_missions_unified(
		view: ObservationView, world: WorldModel, cfg: HeuristicConfig,
		target_planets: list[Planet], threats: list[Threat],
		remaining_steps: int, domination: float
		) -> tuple[list[list[float | int]], list[LaunchDecision]]:
	candidates = []
	planets_by_id = {p.id: p for p in view.planets}
	is_total_war = remaining_steps <= cfg.total_war_remaining_turns

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

			need = world.reinforcement_needed_to_hold_until(
				target_id=target.id, hold_until=hold_until, arrival_turn=probe[1], defender=view.player,
				)
			if not need or need <= 0: continue

			ships_send = max(cfg.min_launch, int(need) + cfg.reinforce_safety_margin)
			ships_send = min(ships_send, available, cap)
			if ships_send < cfg.min_launch: continue

			probe2 = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships_send)
			if not probe2 or probe2[1] > threat.fall_turn or probe2[1] > remaining_steps: continue
			angle, eta = probe2

			if path_collision_predicted(
					src=src, target=target, angle=angle, ships=ships_send, eta=eta, view=view,
					comet_paths=world.comet_paths, comet_path_indices=world.comet_path_indices, skip_own=True,
					): continue

			score = _score_candidate(src, target, ships_send, eta, "reinforce", view, cfg, remaining_steps, domination)
			if score > 0: candidates.append((src, target, angle, ships_send, eta, score, "reinforce"))

	# 2. Build Offense Candidates
	for src in view.my_planets:
		available = int(src.ships) - (0 if is_total_war else cfg.home_reserve)
		if available < cfg.min_launch: continue

		for target in target_planets:
			result = _try_launch(src, target, view, world, cfg, available, domination)
			if not result: continue
			angle, ships, eta = result
			if eta > remaining_steps: continue

			score = _score_candidate(src, target, ships, eta, "capture", view, cfg, remaining_steps, domination)
			if score > 0: candidates.append((src, target, angle, ships, eta, score, "capture"))

	moves, decisions = [], []
	if not candidates: return moves, decisions

	# 3. Resolve using globally optimal constraint dispatch
	if cfg.use_hungarian_offense:
		src_ids = sorted({c[0].id for c in candidates})
		tgt_keys = sorted({(c[1].id, c[6]) for c in candidates})
		src_idx = {sid: i for i, sid in enumerate(src_ids)}
		tgt_idx = {tkey: j for j, tkey in enumerate(tgt_keys)}

		score_matrix = np.zeros((len(src_ids), len(tgt_keys)), dtype=np.float64)
		detail = {}

		for src, target, angle, ships, eta, score, mission in candidates:
			i, j = src_idx[src.id], tgt_idx[(target.id, mission)]
			if score > score_matrix[i, j]:
				score_matrix[i, j] = score
				detail[(i, j)] = (angle, ships, eta, src, target, mission)

		row_ind, col_ind = linear_sum_assignment(score_matrix, maximize=True)

		for i, j in zip(row_ind, col_ind, strict=False):
			if score_matrix[i, j] > 0.0:
				angle, ships, eta, src, target, mission = detail[(i, j)]
				moves.append([src.id, float(angle), int(ships)])
				decisions.append(LaunchDecision(
					src_id=src.id, target_id=target.id, angle=float(angle), ships=int(ships), eta=int(eta),
					src_ships_pre_launch=int(src.ships), target_ships_at_launch=int(target.ships),
					target_owner=int(target.owner), target_x=float(target.x), target_y=float(target.y),
					target_radius=float(target.radius),
					target_is_static=is_static_planet(target.x, target.y, target.radius),
					target_is_comet=view.is_comet(target.id), mission=mission,
					))
	else:
		candidates.sort(key=lambda c: c[5], reverse=True)
		assigned_srcs, assigned_tgts = set(), set()
		for src, target, angle, ships, eta, score, mission in candidates:
			if src.id in assigned_srcs or (target.id, mission) in assigned_tgts: continue
			moves.append([src.id, float(angle), int(ships)])
			decisions.append(LaunchDecision(
				src_id=src.id, target_id=target.id, angle=float(angle), ships=int(ships), eta=int(eta),
				src_ships_pre_launch=int(src.ships), target_ships_at_launch=int(target.ships),
				target_owner=int(target.owner), target_x=float(target.x), target_y=float(target.y),
				target_radius=float(target.radius),
				target_is_static=is_static_planet(target.x, target.y, target.radius),
				target_is_comet=view.is_comet(target.id), mission=mission,
				))
			assigned_srcs.add(src.id)
			assigned_tgts.add((target.id, mission))

	return moves, decisions


def _decide_with_decisions(obs: Any, cfg: HeuristicConfig) -> tuple[list[list[float | int]], list[LaunchDecision]]:
	view = ObservationView.from_raw(obs)
	if not view.my_planets: return [], []
	world = WorldModel.from_observation(view, horizon=cfg.sim_horizon)
	remaining_steps = max(0, EPISODE_STEPS - view.step)
	domination = _get_domination(view)

	target_planets = [p for p in view.planets if p.owner != view.player]
	threats = find_threats(view, world, cfg)

	return _plan_missions_unified(view, world, cfg, target_planets, threats, remaining_steps, domination)