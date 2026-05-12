"""Configured opponent: BEST_V6_OVERHAUL config from CMA-ES sweep 2026-05-09T19-33-22Z.

Source:    docs/research_documents/tuning_runs/2026-05-09T19-33-22Z/best_config.py
Strategy:  orbit_wars.heuristic.heuristic_overhaul.strategy
Fitness:   +0.3651 (4P graduated, post-saturation peak at gen 24, 30-gen sweep,
           ~$27 cost).
Ladder:    NOT YET SUBMITTED at time of vendoring — strength is local-tournament
           only. Field values are corner-of-space in places (comet_value_mult
           ~ 0.023, elimination_bonus ~ 51, reinforce_max_travel_turns = 2,
           total_war_remaining_turns = 5). Treat as a training opponent of
           uncertain quality, not as a strong baseline.

Used by `src/orbit_wars/heuristic/heuristic_overhaul/modal_tuner.py` as a
pre-seeded archive opponent (Option A semantics — see CLAUDE.md history).
Will FIFO-evict from the rolling archive around gen 9 under default
ARCHIVE_MAX_SIZE=3 / ARCHIVE_UPDATE_INTERVAL=3 settings. NOT shipped to
Kaggle.
"""

from orbit_wars.heuristic.heuristic_overhaul.config import HeuristicConfig
from orbit_wars.heuristic.heuristic_overhaul.strategy import agent as _agent_strategy

BEST_V6_OVERHAUL = HeuristicConfig(
    ahead_attack_margin_bonus=0.14113579274904794,
    ahead_domination=0.02106981615952364,
    attack_cost_turn_weight=0.9096296129991575,
    behind_attack_margin_penalty=0.07309856216010595,
    behind_domination=-0.16179301720582684,
    comet_value_mult=0.023396331786186327,
    contested_neutral_value_mult=0.10142563953045676,
    crash_exploit_score_mult=0.1982156020065977,
    defense_buffer=0,
    defense_cost_turn_weight=0.30316940566809436,
    defense_frontier_score_mult=2.544425016157263,
    early_neutral_value_mult=0.8062904190489291,
    early_static_neutral_score_mult=0.2923480822224679,
    early_turn_limit=200,
    elimination_bonus=50.98805322690096,
    finishing_domination=0.4580242418257784,
    finishing_prod_ratio=0.5220997221464737,
    heavy_route_planet_limit=3,
    home_reserve=0,
    hostile_target_value_mult=3.79495221020394,
    late_immediate_ship_value=1.0637051076738895,
    late_remaining_turns=10,
    min_launch=1,
    opening_hostile_target_value_mult=0.2676609648065902,
    opening_turn_limit=10,
    reinforce_cost_turn_weight=2.9890830803796113,
    reinforce_enabled=True,
    reinforce_hold_lookahead=2,
    reinforce_max_source_fraction=0.10317554038333827,
    reinforce_max_travel_turns=2,
    reinforce_min_future_turns=200,
    reinforce_min_production=0,
    reinforce_safety_margin=20,
    reinforce_value_mult=1.8439257133813804,
    rotating_opening_value_mult=0.33708766670183576,
    route_search_horizon=10,
    safe_neutral_value_mult=0.4904516367881282,
    safety_margin=0,
    sim_horizon=250,
    snipe_cost_turn_weight=0.06980890986392477,
    snipe_score_mult=0.42219738676963114,
    soft_act_deadline_fraction=0.3268593029352531,
    static_hostile_value_mult=2.118344571735255,
    static_neutral_value_mult=1.7034029465991838,
    static_target_score_mult=3.505235495527607,
    swarm_score_mult=1.341982819496743,
    total_war_remaining_turns=5,
    use_hungarian_offense=True,
    very_late_remaining_turns=3,
    weak_enemy_threshold=1,
)


def agent(obs):
    return _agent_strategy(obs, BEST_V6_OVERHAUL)


__all__ = ["agent", "BEST_V6_OVERHAUL"]
