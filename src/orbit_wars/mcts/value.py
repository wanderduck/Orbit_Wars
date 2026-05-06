"""Leaf-value estimator for MCTS.

Phase M2: asset-count proxy. Player's value = their assets / total assets
of all alive players. Range [0, 1]; 1 = player owns everything; 0 =
eliminated (or not-yet-eliminated but with no assets).

Phase M4 will replace this with a heuristic-eval-based estimator that's
more accurate but ~100× slower per call.
"""
from __future__ import annotations

from orbit_wars.sim.state import SimState

# Episode terminates at this step per env spec (orbit_wars.json:episodeSteps).
_EPISODE_STEPS = 500


def compute_player_assets(
    state: SimState, *, production_horizon: int = 8
) -> dict[int, float]:
    """Sum each player's planet ships + in-flight fleet ships + production lookahead.

    The production lookahead is critical: at shallow MCTS depths (e.g. 3),
    the simulator can't see far enough for captured planets to "pay back"
    their production. Without weighting future production, the value
    proxy aggressively favors HOLDING ships (no losses) over LAUNCHING
    (some losses + future captures). This biases MCTS toward inaction.

    Mathematically: each owned planet contributes
        ships + production * production_horizon
    where production_horizon=8 represents "we expect to hold this planet
    for ~8 more turns" (calibrated for the 500-step game). Ships in flight
    contribute their face value (no production bonus — they're in transit).

    Neutral (-1) planets contribute to no one.
    """
    assets: dict[int, float] = {}
    for p in state.planets:
        if p.owner != -1:
            value = float(p.ships) + float(p.production) * production_horizon
            assets[p.owner] = assets.get(p.owner, 0.0) + value
    for f in state.fleets:
        assets[f.owner] = assets.get(f.owner, 0.0) + float(f.ships)
    return assets


def is_terminal(state: SimState) -> bool:
    """True iff the game is over.

    Two terminal conditions per env:
      1. step >= EPISODE_STEPS (max length)
      2. Only one alive player (others have no planets and no fleets)
    """
    if state.step >= _EPISODE_STEPS:
        return True
    return len(state.alive_players()) <= 1


def value_estimate(state: SimState, player_id: int) -> float:
    """Estimated value of `state` from `player_id`'s perspective.

    M2 implementation (asset-count proxy):
      - If state is terminal AND player_id is the sole survivor: 1.0
      - If state is terminal AND player_id is eliminated: 0.0
      - Else: assets(player_id) / sum(assets of all alive players),
        clipped to [0, 1].

    The asset-count proxy correlates well with game outcome — the env's
    win condition is "outlast all opponents", which usually traces to
    asset dominance. Noisy per-leaf but averages out across iterations.
    """
    assets = compute_player_assets(state)
    alive = state.alive_players()

    # Terminal short-circuits
    if is_terminal(state):
        if len(alive) == 1:
            return 1.0 if player_id in alive else 0.0
        # Multi-survivor terminal (timeout): use asset share as proxy.
        # Sole-survivor case handled above.

    if not alive:
        return 0.0  # everyone dead (degenerate)

    total = sum(assets.get(p, 0.0) for p in alive)
    if total <= 0.0:
        # All alive players have 0 assets — split equally.
        return 1.0 / len(alive) if player_id in alive else 0.0

    my_assets = assets.get(player_id, 0.0)
    if player_id not in alive:
        return 0.0
    return max(0.0, min(1.0, my_assets / total))
