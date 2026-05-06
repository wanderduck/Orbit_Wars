"""ParamSpace table for CMA-ES tuning of HeuristicConfig.

Massively expanded domain boundaries across all numeric parameters so the
CMA-ES optimizer can organically explore wild tactics without hitting false ceilings.
"""

from __future__ import annotations
from dataclasses import fields
import numpy as np
from orbit_wars.heuristic.config import HeuristicConfig

__all__ = ["PARAM_SPACE", "NUMERIC_FIELDS", "INT_DIM_INDICES", "encode", "decode", "validate_param_space"]

PARAM_SPACE: dict[str, tuple[float, float, bool]] = {
    # ----- Time horizons -----
    "sim_horizon": (20, 250, True),
    "route_search_horizon": (10, 150, True),

    # ----- Mission cost weights -----
    "attack_cost_turn_weight": (0.01, 3.0, False),
    "snipe_cost_turn_weight": (0.01, 3.0, False),
    "defense_cost_turn_weight": (0.01, 3.0, False),
    "reinforce_cost_turn_weight": (0.01, 3.0, False),

    # ----- Value multipliers -----
    "static_neutral_value_mult": (0.1, 5.0, False),
    "static_hostile_value_mult": (0.1, 5.0, False),
    "rotating_opening_value_mult": (0.1, 5.0, False),
    "hostile_target_value_mult": (0.1, 5.0, False),
    "opening_hostile_target_value_mult": (0.1, 5.0, False),
    "safe_neutral_value_mult": (0.1, 5.0, False),
    "contested_neutral_value_mult": (0.1, 5.0, False),
    "early_neutral_value_mult": (0.1, 5.0, False),
    "comet_value_mult": (0.01, 5.0, False),
    "reinforce_value_mult": (0.1, 5.0, False),

    # ----- Send margins -----
    "safety_margin": (0, 15, True),
    "home_reserve": (0, 30, True),
    "min_launch": (1, 100, True),
    "defense_buffer": (0, 15, True),

    # ----- Endgame -----
    "total_war_remaining_turns": (5, 150, True),
    "late_remaining_turns": (10, 200, True),
    "very_late_remaining_turns": (3, 100, True),
    "late_immediate_ship_value": (0.1, 5.0, False),
    "elimination_bonus": (1.0, 100.0, False),
    "weak_enemy_threshold": (1, 200, True),

    # ----- Reinforce mission -----
    "reinforce_min_production": (0, 50, True),
    "reinforce_max_travel_turns": (2, 100, True),
    "reinforce_safety_margin": (0, 20, True),
    "reinforce_max_source_fraction": (0.1, 1.0, False),
    "reinforce_min_future_turns": (3, 200, True),
    "reinforce_hold_lookahead": (2, 100, True),

    # ----- Time budget -----
    "soft_act_deadline_fraction": (0.3, 0.99, False),
    "heavy_route_planet_limit": (3, 150, True),

    # ----- Opening / phase markers -----
    "early_turn_limit": (3, 200, True),
    "opening_turn_limit": (10, 300, True),

    # ----- Score multipliers -----
    "static_target_score_mult": (0.1, 5.0, False),
    "early_static_neutral_score_mult": (0.1, 5.0, False),
    "snipe_score_mult": (0.1, 5.0, False),
    "swarm_score_mult": (0.1, 5.0, False),
    "crash_exploit_score_mult": (0.1, 5.0, False),
    "defense_frontier_score_mult": (0.1, 5.0, False),

    # ----- Domination thresholds -----
    "behind_domination": (-0.8, 0.0, False),
    "ahead_domination": (0.0, 0.8, False),
    "finishing_domination": (0.1, 0.9, False),
    "finishing_prod_ratio": (0.5, 5.0, False),
    "behind_attack_margin_penalty": (0.0, 0.8, False),
    "ahead_attack_margin_bonus": (0.0, 0.8, False),
}

NUMERIC_FIELDS: list[str] = list(PARAM_SPACE.keys())
INT_DIM_INDICES: list[int] = [i for i, name in enumerate(NUMERIC_FIELDS) if PARAM_SPACE[name][2]]

def validate_param_space() -> None:
    numeric_field_names = {f.name for f in fields(HeuristicConfig) if f.type in (int, float, "int", "float")}
    missing = numeric_field_names - set(PARAM_SPACE)
    if missing: raise ValueError(f"Missing bounds for: {sorted(missing)}")

def encode(cfg: HeuristicConfig) -> np.ndarray:
    return np.array([float(getattr(cfg, name)) for name in NUMERIC_FIELDS], dtype=np.float64)

def decode(x: np.ndarray) -> HeuristicConfig:
    kwargs: dict[str, int | float] = {}
    for i, name in enumerate(NUMERIC_FIELDS):
        _, _, is_int = PARAM_SPACE[name]
        kwargs[name] = int(round(float(x[i]))) if is_int else float(x[i])
    return HeuristicConfig(**kwargs)