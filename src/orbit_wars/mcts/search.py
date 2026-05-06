"""SM-MCTS search loop with decoupled UCT.

Phase M3 implementation per design v2 §3.1 and §4 M3:
  - Decoupled UCT: each player picks argmax UCB INDEPENDENTLY at each node
  - Progressive Widening: k_pw = ceil(WIDEN_C * visits^WIDEN_ALPHA)
  - First-Play Urgency (FPU): unvisited score = cfg.fpu_c (not +inf)
  - Robust child: root pick = argmax visits (not argmax mean)
  - Joint action drives simulator.step() to advance to child
  - Asset-count proxy at leaf for value
  - Time-bounded iteration loop

M4 will swap value estimator to heuristic-eval at leaves.
M5 will JIT-compile the simulator hot path.
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
    fpu_c: float,
) -> float:
    """UCB1 with First-Play Urgency (FPU).

    Per Aljabasini 2021 §2.1.1 / Algorithm 1 commentary: vanilla MCTS
    treats unvisited actions as ``+inf``, forcing one visit to each
    before any exploitation. FPU replaces ``+inf`` with a constant
    ``fpu_c`` (default 0.5) — "we don't know yet, assume average".
    Critical at shallow budgets where many actions never get a single
    visit; without FPU, MCTS spends all its budget round-robin'ing
    over unvisited actions instead of deepening on promising ones.
    """
    if visits <= 0:
        return fpu_c
    mean = value_sum / visits
    explore = ucb_c * math.sqrt(math.log(max(parent_visits, 1)) / visits)
    return mean + explore


def _pw_action_count(visits: int, cfg: MCTSConfig) -> int:
    """Progressive Widening: how many of the ranked actions to consider
    at a node with ``visits`` total visits.

    ``k = ceil(WIDEN_C * visits^WIDEN_ALPHA)``  (Aljabasini Algorithm 2).

    With WIDEN_C=2, WIDEN_ALPHA=0.5:
      visits=0  → k=2 (start with 2 best actions)
      visits=1  → k=2
      visits=4  → k=4
      visits=16 → k=8
      visits=64 → k=16

    Forces MCTS to focus early visits on top-ranked actions; only
    considers more (lower-ranked) actions as visit count grows. This
    is what makes MCTS work in huge action spaces — without PW, the
    budget is wasted exploring low-quality moves that the heuristic
    ranking already flagged as unpromising.
    """
    if visits <= 0:
        return max(1, int(math.ceil(cfg.widen_c)))
    return max(1, int(math.ceil(cfg.widen_c * (visits ** cfg.widen_alpha))))


def _select_action_for(
    node: MCTSNode,
    player_id: int,
    cfg: MCTSConfig,
) -> int:
    """Pick action_idx for ``player_id`` at ``node`` via PW + FPU UCB1.

    Returns an action_idx in range ``[0, min(k_pw, len(actions)))``.
    Caller must ensure ``node.ranked_actions[player_id]`` is populated.

    M3 changes vs M2:
      - PW limits considered actions to top-k where k grows with
        node.visits (was: all ``len(actions)``).
      - FPU uses ``cfg.fpu_c`` for unvisited (was: ``+inf``).
    """
    actions = node.ranked_actions[player_id]
    if len(actions) == 1:
        return 0  # only "hold" available — trivial

    # Progressive Widening: consider only top-k ranked actions
    k = min(_pw_action_count(node.visits, cfg), len(actions))

    best_idx = 0
    best_score = -math.inf
    for idx in range(k):
        v, vsum = node.get_stat(player_id, idx)
        score = _ucb_score(v, vsum, node.visits, cfg.ucb_c, cfg.fpu_c)
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

    # Pick our player's best action_idx at root via ROBUST CHILD selection
    # (Aljabasini §2.1.1 paragraph after Algorithm 1):
    #
    #   "Most recent works opt for selecting the child who has been visited
    #    the most, as this kind of selection is more robust compared to
    #    other approaches (which is the reason this method is sometimes
    #    called robust child)."
    #
    # M3 change vs M2: argmax visits (not argmax mean). Visits-based picks
    # are less brittle to outlier rollouts that inflate the mean of a
    # rarely-visited action.
    our_actions = root.ranked_actions.get(our_player, [[]])
    if not our_actions:
        return [], {"iterations": iterations, "fallback": "no_actions"}

    best_idx = 0
    best_visits = -1
    best_mean = 0.0
    for idx in range(len(our_actions)):
        v, vsum = root.get_stat(our_player, idx)
        if v > best_visits:
            best_visits = v
            best_idx = idx
            best_mean = (vsum / v) if v > 0 else 0.0
    # Fallback: if ABSOLUTELY no visits (out of time at the very first
    # iteration), default to variant 0 (heuristic action at root).
    if best_visits <= 0:
        best_idx = 0
        best_mean = 0.0

    chosen = our_actions[best_idx]
    debug = {
        "iterations": iterations,
        "root_visits": root.visits,
        "our_action_idx": best_idx,
        "our_action_visits": best_visits,
        "our_mean_value": best_mean,
        "elapsed_s": time.perf_counter() - started,
    }
    return chosen, debug
