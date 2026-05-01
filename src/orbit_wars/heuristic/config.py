"""HeuristicConfig — tunable weights and thresholds for the v1 heuristic agent.

Initial values lifted from E6 (pilkwang structured baseline) per synthesis §5.B,
with E9's ``TOTAL_WAR_REMAINING_TURNS = 55`` adopted per §5.A. Use ``# was X``
audit-trail comments when tuning (per E9's convention) so the value's history
is co-located with the value.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["HeuristicConfig"]


@dataclass(frozen=True, slots=True)
class HeuristicConfig:
    # ----- Time horizons -----
    sim_horizon: int = 110              # E6 — timeline projection length
    route_search_horizon: int = 60      # E6 — max ETA we consider for a launch

    # ----- Mission cost weights (denominator: send + turns*cost_w + 1) -----
    attack_cost_turn_weight: float = 0.55       # E6
    snipe_cost_turn_weight: float = 0.45        # E6
    defense_cost_turn_weight: float = 0.40      # E6
    reinforce_cost_turn_weight: float = 0.35    # E6

    # ----- Value multipliers -----
    static_neutral_value_mult: float = 1.4      # E6
    static_hostile_value_mult: float = 1.55     # E6
    rotating_opening_value_mult: float = 0.9    # E6
    hostile_target_value_mult: float = 1.85     # E6
    opening_hostile_target_value_mult: float = 1.45
    safe_neutral_value_mult: float = 1.2
    contested_neutral_value_mult: float = 0.7
    early_neutral_value_mult: float = 1.2
    comet_value_mult: float = 0.65              # E6
    reinforce_value_mult: float = 1.35          # E8 / E9

    # ----- Send margins -----
    safety_margin: int = 1                      # was 2,1,0 — slight buffer
    home_reserve: int = 0                       # was 5,2,0 — early game wants full aggression
    min_launch: int = 20                        # was 6,3,1 — match sniper baseline (fleet_speed(20)≈2.55, fast enough)
    defense_buffer: int = 2

    # ----- Endgame -----
    total_war_remaining_turns: int = 55         # was 38 — E9 explicit tuning note
    late_remaining_turns: int = 60              # E6
    very_late_remaining_turns: int = 25         # E6
    late_immediate_ship_value: float = 0.6      # E6
    elimination_bonus: float = 18.0             # E6
    weak_enemy_threshold: int = 45              # E6

    # ----- Reinforce mission -----
    reinforce_enabled: bool = True
    reinforce_min_production: int = 2
    reinforce_max_travel_turns: int = 22
    reinforce_safety_margin: int = 2
    reinforce_max_source_fraction: float = 0.75
    reinforce_min_future_turns: int = 40
    reinforce_hold_lookahead: int = 20

    # ----- Offense planner -----
    # `True` uses scipy linear_sum_assignment (Hungarian) for one-to-one optimal
    # src→target matching. `False` falls back to v1.4-style greedy: each src
    # picks its nearest viable target. Default switched to greedy in v1.5G —
    # v1.5 (Hungarian + defense) had regressed -100 μ on Kaggle vs v1.4
    # (greedy, no defense), and local opponents don't differentiate the two,
    # so we ship the offense planner that matched v1.4's 700.5 score and add
    # defense on top for a controlled A/B against the deployed v1.5.
    use_hungarian_offense: bool = False

    # ----- Time budget -----
    soft_act_deadline_fraction: float = 0.82    # E6 — act with 82% of max_time
    heavy_route_planet_limit: int = 32          # E6

    # ----- Opening / phase markers -----
    early_turn_limit: int = 40                  # E6
    opening_turn_limit: int = 80                # E6

    # ----- Sun avoidance — adopted from geometry module defaults -----
    # (SUN_RADIUS=10.0, SUN_SAFETY=1.5, MAX_SPEED=6.0 live in `orbit_wars.geometry`)

    # ----- Score multipliers (post-cost-ratio) -----
    static_target_score_mult: float = 1.18      # E6
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

    @classmethod
    def default(cls) -> HeuristicConfig:
        return cls()
