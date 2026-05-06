"""SM-MCTS search loop with decoupled UCT.

Phase M2 implementation per design v2 §3.1 and §4 M2:
  - Decoupled UCT: each player picks argmax UCB INDEPENDENTLY at each node
  - Joint action drives simulator.step() to advance to child
  - Asset-count proxy at leaf for value
  - Fixed k = config.fixed_k_per_player (no Progressive Widening yet)
  - Vanilla UCB1 (no FPU yet) — unvisited gets +inf
  - Time-bounded iteration loop; root selection via mean value (not robust child)

M3 will add Progressive Widening + FPU + robust child. M4 will swap value
estimator to heuristic-eval. M5 will JIT-compile the simulator hot path.
"""
from __future__ import annotations

import math
import time
from typing import Callable

from orbit_wars.sim.action import Action
from orbit_wars.sim.simulator import Simulator
from orbit_wars.sim.state import SimState

from .config import MCTSConfig
from .node import JointAction, MCTSNode
from .ranking import (
    ActionList,
    ranked_actions_for,
    ranked_actions_with_heuristic,
)
from .value import is_terminal, value_estimate


def _action_list_to_actions(
    action_list: ActionList,
) -> list[Action]:
    """Convert env-format moves [from_id, angle, ships] to typed Actions."""
    return [Action.from_env_format(move) for move in action_list]


def _ucb_score(
    visits: int,
    value_sum: float,
    parent_visits: int,
    ucb_c: float,
) -> float:
    """Standard UCB1. Unvisited returns +inf for vanilla M2 (no FPU yet)."""
    if visits <= 0:
        return math.inf
    mean = value_sum / visits
    explore = ucb_c * math.sqrt(math.log(max(parent_visits, 1)) / visits)
    return mean + explore


def _select_action_for(
    node: MCTSNode,
    player_id: int,
    cfg: MCTSConfig,
) -> int:
    """Pick action_idx for `player_id` at `node` via UCB1.

    Returns an action_idx in range [0, k). Caller must ensure
    `node.ranked_actions[player_id]` is populated first.
    """
    actions = node.ranked_actions[player_id]
    if len(actions) == 1:
        return 0  # only "hold" available — trivial
    best_idx = 0
    best_score = -math.inf
    for idx in range(len(actions)):
        v, vsum = node.get_stat(player_id, idx)
        score = _ucb_score(v, vsum, node.visits, cfg.ucb_c)
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def _simmcts_iteration(
    node: MCTSNode,
    sim: Simulator,
    cfg: MCTSConfig,
    our_player: int,
    depth: int,
) -> dict[int, float]:
    """One SM-MCTS iteration starting from `node`. Returns per-player values
    backed up the path (positive for the player's perspective).

    Recursive — each call either:
      a) Hits a terminal/depth limit → returns leaf value
      b) Reaches an unexpanded joint action → expands + leaf value
      c) Recurses into existing child
    """
    # Terminal / depth limit → leaf value
    if depth >= cfg.max_depth or is_terminal(node.state):
        return {p: value_estimate(node.state, p) for p in node.state.alive_players()}

    # Lazy-load ranked actions for every alive player at this node
    alive = list(node.state.alive_players())
    for p in alive:
        node.get_ranked(p, ranked_actions_for, cfg.fixed_k_per_player)

    # Decoupled UCT: each alive player independently picks an action_idx
    joint_indices = tuple(
        _select_action_for(node, p, cfg) for p in alive
    )

    # Build env-format actions for simulator step
    env_actions: dict[int, list[Action]] = {}
    for p, idx in zip(alive, joint_indices):
        action_list = node.ranked_actions[p][idx]
        env_actions[p] = _action_list_to_actions(action_list)

    # JointAction key includes player_id ordering for deterministic dict lookup
    joint_key: JointAction = joint_indices

    # Expand or recurse
    if joint_key not in node.children:
        # Expansion: step the sim, create child, evaluate leaf
        next_state = sim.step(node.state, env_actions)
        child = MCTSNode(state=next_state)
        node.children[joint_key] = child
        leaf_values = {p: value_estimate(next_state, p) for p in alive}
    else:
        # Selection: recurse into existing child
        child = node.children[joint_key]
        leaf_values = _simmcts_iteration(
            child, sim, cfg, our_player, depth + 1
        )

    # Backprop: update this node's per-player stats for the actions taken
    node.visits += 1
    for p, idx in zip(alive, joint_indices):
        v = leaf_values.get(p, 0.0)
        node.update_stat(p, idx, v)

    return leaf_values


def search(
    state: SimState,
    cfg: MCTSConfig,
    our_player: int,
    *,
    deadline_s: float | None = None,
) -> tuple[ActionList, dict]:
    """Run SM-MCTS for ``cfg.turn_budget_ms`` (or until ``deadline_s``).

    Returns ``(best_action_list, debug)`` where:
      - best_action_list is the env-format action list our_player should submit
      - debug is a small dict with stats (iterations, root visits, etc.)
    """
    sim = Simulator()
    root = MCTSNode(state=state)
    started = time.perf_counter()
    if deadline_s is None:
        deadline_s = started + cfg.turn_budget_ms / 1000.0

    # Pre-populate ROOT actions for ALL alive players with the heuristic-
    # augmented ranker. Variant 0 = full heuristic action → MCTS's
    # worst-case pick at root is heuristic-equivalent. Inner nodes use
    # the lightweight ranker (lazy via node.get_ranked) to keep iteration
    # cost low. See ranking.py for the rationale.
    for p in state.alive_players():
        root.ranked_actions[p] = ranked_actions_with_heuristic(
            state, p, k=cfg.fixed_k_per_player
        )

    iterations = 0
    while time.perf_counter() < deadline_s:
        _simmcts_iteration(root, sim, cfg, our_player, depth=0)
        iterations += 1

    # Pick our player's best action_idx at root.
    # M2: vanilla "highest mean value" (M3 will add robust-child).
    our_actions = root.ranked_actions.get(our_player, [[]])
    if not our_actions:
        return [], {"iterations": iterations, "fallback": "no_actions"}

    best_idx = 0
    best_mean = -math.inf
    for idx in range(len(our_actions)):
        v, vsum = root.get_stat(our_player, idx)
        if v <= 0:
            # Unvisited — skip; would cause divide-by-zero. UCB1's exploration
            # at root should have visited each at least once unless we ran out
            # of time.
            continue
        mean = vsum / v
        if mean > best_mean:
            best_mean = mean
            best_idx = idx

    chosen = our_actions[best_idx]
    debug = {
        "iterations": iterations,
        "root_visits": root.visits,
        "our_action_idx": best_idx,
        "our_mean_value": best_mean,
        "elapsed_s": time.perf_counter() - started,
    }
    return chosen, debug
