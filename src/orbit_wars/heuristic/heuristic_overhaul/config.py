"""HeuristicConfig   tunable weights and thresholds for the v2 heuristic agent."""

from __future__ import annotations
from dataclasses import dataclass

__all__ = ["HeuristicConfig"]


@dataclass(frozen=True, slots=True)
class HeuristicConfig:
    # ----- Time horizons -----
    sim_horizon: int = 110
    route_search_horizon: int = 60

    # ----- Mission cost weights (denominator: send + turns*cost_w + 1) -----
    attack_cost_turn_weight: float = 0.55
    snipe_cost_turn_weight: float = 0.45
    defense_cost_turn_weight: float = 0.40
    reinforce_cost_turn_weight: float = 0.35

    # ----- Value multipliers -----
    static_neutral_value_mult: float = 1.4
    static_hostile_value_mult: float = 1.55
    rotating_opening_value_mult: float = 0.9
    hostile_target_value_mult: float = 1.85
    opening_hostile_target_value_mult: float = 1.45
    safe_neutral_value_mult: float = 1.2
    contested_neutral_value_mult: float = 0.7
    early_neutral_value_mult: float = 1.2
    comet_value_mult: float = 0.65
    reinforce_value_mult: float = 1.35

    # ----- Send margins -----
    safety_margin: int = 1
    home_reserve: int = 0
    min_launch: int = 20
    defense_buffer: int = 2

    # ----- Endgame -----
    total_war_remaining_turns: int = 55
    late_remaining_turns: int = 60
    very_late_remaining_turns: int = 25
    late_immediate_ship_value: float = 0.6
    elimination_bonus: float = 18.0
    weak_enemy_threshold: int = 45

    # ----- Reinforce mission -----
    reinforce_enabled: bool = True
    reinforce_min_production: int = 2
    reinforce_max_travel_turns: int = 22
    reinforce_safety_margin: int = 2
    reinforce_max_source_fraction: float = 0.75
    reinforce_min_future_turns: int = 40
    reinforce_hold_lookahead: int = 20

    # ----- Offense planner -----
    # Default switched to True; Hungarian matching is now mathematically superior
    # to greedy due to the Unified dynamic scoring engine.
    use_hungarian_offense: bool = True

    # ----- Time budget -----
    soft_act_deadline_fraction: float = 0.82
    heavy_route_planet_limit: int = 32

    # ----- Opening / phase markers -----
    early_turn_limit: int = 40
    opening_turn_limit: int = 80

    # ----- Score multipliers (post-cost-ratio) -----
    static_target_score_mult: float = 1.18
    early_static_neutral_score_mult: float = 1.25
    snipe_score_mult: float = 1.12
    swarm_score_mult: float = 1.06
    crash_exploit_score_mult: float = 1.05
    defense_frontier_score_mult: float = 1.12

    # ----- Domination thresholds -----
    behind_domination: float = -0.20
    ahead_domination: float = 0.18
    finishing_domination: float = 0.35
    finishing_prod_ratio: float = 1.25
    behind_attack_margin_penalty: float = 0.05
    ahead_attack_margin_bonus: float = 0.08

    # ----- Exposed Planet Detection -----
    exposed_planet_min_outbound: int = 15
    exposed_planet_min_fleet_ships: int = 5
    exposed_planet_value_mult: float = 1.30
    exposed_planet_margin_relief: int = 2

    # ----- Spatial & Distance Thresholds -----
    defense_frontier_distance: float = 15.0
    safe_contested_neutral_margin: float = 15.0
    backline_safe_distance: float = 35.0
    redistribute_min_dist_diff: float = 20.0
    redistribute_scale_factor: float = 15.0

    # ----- Target Size Thresholds -----
    snipe_ships_threshold: int = 10
    swarm_min_fleet_size: int = 50
    swarm_overkill_ratio: float = 0.3

    @classmethod
    def default(cls) -> HeuristicConfig:
        return cls()