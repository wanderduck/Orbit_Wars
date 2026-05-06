"""Move-ordering function for MCTS Progressive Widening.

Phase M2 implementation (DEVIATION FROM DESIGN v2 §3.2):
The design specified using the heuristic agent's per-launch scoring as
the move-ordering function. In practice, calling the full heuristic
costs ~10-20ms per call, and we'd need K calls per node (one per
player) — that's 40-80ms PER NEW MCTS NODE. With a 700ms turn budget
and ~7ms target per iteration, we can only afford 1-2 new nodes per
turn → tree barely grows.

Resolution for M2: use a **lightweight nearest-target ranker** that runs
in ~0.5-1ms per player. Less accurate than the full heuristic but fast
enough to call per node. Phase M4 may revisit this when heuristic-eval-
at-leaf becomes the dominant per-iteration cost.

The ranker produces COMPOUND ACTION LISTS (full ``list[list[float|int]]``
to submit to env), not individual launches. Each variant is a different
combination of launches across the player's owned planets.

Variants returned (order matters — index 0 = best):
  0. ALL: launch from every owned planet at its nearest enemy/neutral
  1. HOLD: empty action list (no launches this turn)
  2..K: drop one launch from variant 0 (one per owned planet, scaled to K)
"""
from __future__ import annotations

import math
from typing import Any

from orbit_wars.sim.state import SimState

# An action is a single launch: [from_planet_id, angle, ships]. Same shape
# the env's `agent` returns.
ActionMove = list[Any]
# A full per-turn action for one player: list of launches.
ActionList = list[ActionMove]


def _compute_base_launches(
    state: SimState, player_id: int, *, min_launch: int = 5
) -> ActionList:
    """For each owned planet with sufficient ships, generate the
    "launch at nearest enemy/neutral" action.

    Returns a list of launches sorted by source planet ID (deterministic).
    Empty if no eligible planet/target combos exist.
    """
    owned = [
        p for p in state.planets
        if p.owner == player_id and p.ships >= min_launch
    ]
    if not owned:
        return []

    # Targets: enemies first, then neutrals
    enemies = [
        p for p in state.planets
        if p.owner != player_id and p.owner != -1
    ]
    neutrals = [p for p in state.planets if p.owner == -1]
    candidates = enemies + neutrals
    if not candidates:
        return []

    launches: ActionList = []
    for src in sorted(owned, key=lambda p: p.id):
        # Pick nearest by squared L2 distance — cheap, good enough for ordering
        nearest = min(
            candidates,
            key=lambda t: (t.x - src.x) ** 2 + (t.y - src.y) ** 2,
        )
        angle = math.atan2(nearest.y - src.y, nearest.x - src.x)
        # Send half the available ships, integer
        ships = int(max(min_launch, src.ships // 2))
        if ships <= 0 or ships > src.ships:
            continue
        launches.append([src.id, float(angle), ships])
    return launches


def ranked_actions_for(
    state: SimState, player_id: int, k: int = 8
) -> list[ActionList]:
    """Return up to ``k`` candidate compound actions for ``player_id``,
    ranked from best (index 0) to worst (index k-1).

    Always at least 1 element ("hold" / empty list). Variants beyond what
    the player can meaningfully choose (e.g., 2-launch player can't have
    K=8 distinct drop-one variants) are truncated; caller should not
    assume exactly K returned.

    See module docstring for the M2 lightweight ranker rationale.
    """
    base = _compute_base_launches(state, player_id)

    if not base:
        # No launches possible — only "hold" is a valid choice.
        return [[]]

    # Variant 0: all launches together (heuristic top-1 proxy)
    variants: list[ActionList] = [base]

    # Variant 1: hold (empty) — keeps an option to wait
    variants.append([])

    # Variants 2..k: drop one launch each (creates partial-launch options)
    # Order by source planet id (deterministic) so reproducible.
    n_drop_variants = min(k - len(variants), len(base))
    for i in range(n_drop_variants):
        variants.append([m for j, m in enumerate(base) if j != i])

    return variants[:k]


def get_heuristic_action_for(state: SimState, player_id: int) -> ActionList:
    """Call the full heuristic agent from `player_id`'s perspective.

    Used at the ROOT of the MCTS tree (per design v2 §3.2 + M2 deviation
    note: too slow to call per inner node). Cost ~10-20ms per call. With
    4 players, ~40-80ms one-time at root — acceptable share of the 700ms
    turn budget.

    Returns the env-format action list the heuristic would submit if
    `player_id` were the agent at this state.
    """
    # Lazy imports to keep this module cheap when ranking is used standalone.
    from orbit_wars.heuristic.strategy import agent as heuristic_agent
    from orbit_wars.sim.validator import _simstate_to_env_dict

    obs_dict = _simstate_to_env_dict(state)
    obs_dict["player"] = player_id
    obs_dict["remainingOverageTime"] = 60.0  # arbitrary; heuristic doesn't use
    return heuristic_agent(obs_dict, None)


def ranked_actions_with_heuristic(
    state: SimState, player_id: int, k: int = 8
) -> list[ActionList]:
    """Like `ranked_actions_for` but variant 0 is the FULL HEURISTIC's action.

    This guarantees MCTS's worst-case pick at the root is equivalent to
    the heuristic's pick. If MCTS picks variant 0, we behave exactly like
    the heuristic. If MCTS picks variant 1+, it has statistical evidence
    that the alternative is better.

    Use ONLY at the root (cost ~10-20ms per player); inner nodes should use
    `ranked_actions_for` (lightweight only).
    """
    heur_action = get_heuristic_action_for(state, player_id)
    light_variants = ranked_actions_for(state, player_id, k=k)

    # Variant 0 = heuristic. Variants 1..K-1 = lightweight (skipping its
    # variant 0 which would otherwise duplicate heuristic when both pick
    # similar moves; instead include hold + drop-one variants).
    if len(light_variants) <= 1:
        # Light gave only "hold" → use heuristic + hold
        return [heur_action, []] if heur_action else [[]]
    return [heur_action] + light_variants[1:k]
