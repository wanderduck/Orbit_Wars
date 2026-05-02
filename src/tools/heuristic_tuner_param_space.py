"""ParamSpace table for CMA-ES tuning of HeuristicConfig.

48 numeric fields. Each entry is (lower, upper, is_int).

Booleans (`reinforce_enabled`, `use_hungarian_offense`) are NOT in the table —
they're pinned at v1.5G defaults per the spec.

Bound philosophy (from ParamSpace_meta.md): wide enough to let CMA-ES explore
qualitatively different strategies, but constrained by gameplay sanity (e.g.
min_launch >= 1; multipliers >= 0; turn-counters within episode length 500).
"""

from __future__ import annotations

from dataclasses import fields

import numpy as np

from orbit_wars.heuristic.config import HeuristicConfig

__all__ = [
    "PARAM_SPACE",
    "NUMERIC_FIELDS",
    "INT_DIM_INDICES",
    "encode",
    "decode",
    "validate_param_space",
]

# (lower, upper, is_int) per field — 48 entries
PARAM_SPACE: dict[str, tuple[float, float, bool]] = {
    # ----- Time horizons -----
    "sim_horizon": (40, 200, True),
    "route_search_horizon": (20, 120, True),

    # ----- Mission cost weights -----
    "attack_cost_turn_weight": (0.1, 1.5, False),
    "snipe_cost_turn_weight": (0.1, 1.5, False),
    "defense_cost_turn_weight": (0.1, 1.5, False),
    "reinforce_cost_turn_weight": (0.1, 1.5, False),

    # ----- Value multipliers -----
    "static_neutral_value_mult": (0.3, 3.0, False),
    "static_hostile_value_mult": (0.3, 3.0, False),
    "rotating_opening_value_mult": (0.2, 2.5, False),
    "hostile_target_value_mult": (0.5, 3.5, False),
    "opening_hostile_target_value_mult": (0.3, 3.0, False),
    "safe_neutral_value_mult": (0.3, 2.5, False),
    "contested_neutral_value_mult": (0.2, 2.0, False),
    "early_neutral_value_mult": (0.3, 2.5, False),
    "comet_value_mult": (0.1, 2.0, False),
    "reinforce_value_mult": (0.5, 3.0, False),

    # ----- Send margins -----
    "safety_margin": (0, 5, True),
    "home_reserve": (0, 10, True),
    "min_launch": (5, 50, True),
    "defense_buffer": (0, 8, True),

    # ----- Endgame -----
    "total_war_remaining_turns": (15, 100, True),
    "late_remaining_turns": (20, 120, True),
    "very_late_remaining_turns": (10, 60, True),
    "late_immediate_ship_value": (0.1, 2.0, False),
    "elimination_bonus": (5.0, 40.0, False),
    "weak_enemy_threshold": (10, 100, True),

    # ----- Reinforce mission -----
    "reinforce_min_production": (0, 10, True),
    "reinforce_max_travel_turns": (5, 60, True),
    "reinforce_safety_margin": (0, 8, True),
    "reinforce_max_source_fraction": (0.2, 0.95, False),
    "reinforce_min_future_turns": (10, 100, True),
    "reinforce_hold_lookahead": (5, 60, True),

    # ----- Time budget -----
    "soft_act_deadline_fraction": (0.5, 0.95, False),
    "heavy_route_planet_limit": (8, 80, True),

    # ----- Opening / phase markers -----
    "early_turn_limit": (10, 100, True),
    "opening_turn_limit": (30, 150, True),

    # ----- Score multipliers -----
    "static_target_score_mult": (0.5, 2.5, False),
    "early_static_neutral_score_mult": (0.5, 2.5, False),
    "snipe_score_mult": (0.5, 2.5, False),
    "swarm_score_mult": (0.5, 2.5, False),
    "crash_exploit_score_mult": (0.5, 2.5, False),
    "defense_frontier_score_mult": (0.5, 2.5, False),

    # ----- Domination thresholds -----
    "behind_domination": (-0.5, 0.0, False),
    "ahead_domination": (0.0, 0.5, False),
    "finishing_domination": (0.1, 0.7, False),
    "finishing_prod_ratio": (1.0, 2.5, False),
    "behind_attack_margin_penalty": (0.0, 0.3, False),
    "ahead_attack_margin_bonus": (0.0, 0.3, False),
}

# Stable ordering of tunable fields (matches PARAM_SPACE insertion order)
NUMERIC_FIELDS: list[str] = list(PARAM_SPACE.keys())

# Indices into the encoded vector that correspond to integer fields
INT_DIM_INDICES: list[int] = [
    i for i, name in enumerate(NUMERIC_FIELDS)
    if PARAM_SPACE[name][2]
]


def validate_param_space() -> None:
    """Fail-loud check: every numeric HeuristicConfig field must be in PARAM_SPACE.

    Called by tests; called also at tuner startup to catch config drift.
    """
    numeric_field_names = {
        f.name for f in fields(HeuristicConfig)
        if f.type in (int, float, "int", "float")
    }
    missing = numeric_field_names - set(PARAM_SPACE)
    extra = set(PARAM_SPACE) - numeric_field_names
    if missing:
        raise ValueError(
            f"PARAM_SPACE missing bounds for HeuristicConfig fields: {sorted(missing)}. "
            f"Add them to PARAM_SPACE in src/tools/heuristic_tuner_param_space.py."
        )
    if extra:
        raise ValueError(
            f"PARAM_SPACE has bounds for fields that don't exist on HeuristicConfig: "
            f"{sorted(extra)}. Did a field get renamed?"
        )


def encode(cfg: HeuristicConfig) -> np.ndarray:
    """HeuristicConfig → flat float vector in NUMERIC_FIELDS order."""
    return np.array([float(getattr(cfg, name)) for name in NUMERIC_FIELDS], dtype=np.float64)


def decode(x: np.ndarray) -> HeuristicConfig:
    """Float vector → HeuristicConfig. Integer fields are rounded; bools use defaults."""
    if x.shape != (len(NUMERIC_FIELDS),):
        raise ValueError(
            f"decode: expected shape ({len(NUMERIC_FIELDS)},), got {x.shape}"
        )
    kwargs: dict[str, int | float] = {}
    for i, name in enumerate(NUMERIC_FIELDS):
        _, _, is_int = PARAM_SPACE[name]
        kwargs[name] = int(round(float(x[i]))) if is_int else float(x[i])
    return HeuristicConfig(**kwargs)
