"""SM-MCTS search loop with decoupled UCT.

This module hosts BOTH the legacy compound-variant search (M3) and the
option-2 single-launch-token search. The public ``search()`` function is
a dispatcher keyed on ``cfg.use_token_variants``.

Legacy path (use_token_variants=False, default):
  - Decoupled UCT: each player picks argmax UCB INDEPENDENTLY at each node
  - Progressive Widening: k_pw = ceil(WIDEN_C * visits^WIDEN_ALPHA)
  - First-Play Urgency (FPU): unvisited score = cfg.fpu_c (not +inf)
  - Robust child: root pick = argmax visits (not argmax mean)
  - Joint action = one compound action list per player
  - Asset-count proxy at leaf for value
  - Time-bounded iteration loop

Option-2 path (use_token_variants=True):
  - Per-env-turn launch SUB-TREE: each MCTS sub-step picks ONE launch token
    per alive, not-yet-committed player
  - Sub-tree leaves are reached when both players COMMIT (or hit
    cfg.max_launches_per_turn cap) — at that point Simulator.step advances
    ONE env-turn
  - Stats live at the SUB-NODE level (per-player per-token UCB)
  - Robust child at root = most-visited COMMITTED CHILD (per design open Q1)
  - See docs/research_documents/2026-05-06-mcts-option2-tokens-design.md

M4 will swap value estimator to heuristic-eval at leaves.
M5 will JIT-compile the simulator hot path.
"""
from __future__ import annotations

import math
import time

from orbit_wars.sim.action import Action
from orbit_wars.sim.simulator import Simulator
from orbit_wars.sim.state import SimState

from .config import MCTSConfig
from .node import MCTSNode
from .node_tokens import (
    MCTSNode as TokenMCTSNode,
)
from .node_tokens import (
    SubNode,
    canonicalize_committed,
    make_subnode_key,
)
from .ranking import (
    ActionList,
    ranked_actions_for,
    ranked_actions_with_heuristic,
)
from .serialize import serialize_picks_to_env_actions
from .token import LaunchToken
from .tokens import generate_ranked_tokens
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
    """Public entry point. Dispatches on ``cfg.use_token_variants``.

    ``False`` (default) → legacy compound-variant search (M3).
    ``True`` → option-2 single-launch-token sub-tree search.

    Returns ``(best_action_list, debug)``.
    """
    if cfg.use_token_variants:
        return _search_tokens(state, cfg, our_player, deadline_s=deadline_s)
    return _search_legacy(state, cfg, our_player, deadline_s=deadline_s)


def _search_legacy(
    state: SimState,
    cfg: MCTSConfig,
    our_player: int,
    *,
    deadline_s: float | None = None,
) -> tuple[ActionList, dict]:
    """Legacy compound-variant search (M3 implementation).

    Each MCTS step picks one variant per player from a compound action list.
    See module docstring for the full description.
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


# ===========================================================================
# Option-2 sub-tree search (use_token_variants=True)
# ===========================================================================


# Conventional value used in unit tests where token lists are constructed
# manually with COMMIT at index 0. Production code uses _find_commit_idx
# (token list may have COMMIT at any position depending on cfg.commit_position).
_COMMIT_IDX = 0


def _find_commit_idx(tokens: list[LaunchToken]) -> int:
    """Return the index of the COMMIT sentinel in ``tokens``. Generator
    convention: COMMIT is at index 0 (cfg.commit_position="first") or at
    len(tokens)-1 (cfg.commit_position="last"). Returns 0 if no COMMIT
    found, which would be a generator bug — defensive."""
    for idx, t in enumerate(tokens):
        if t.is_commit():
            return idx
    return 0


def _filter_valid_token_indices(
    tokens: list[LaunchToken],
    prior_picks: tuple[int, ...],
    state: SimState,
    player_id: int,
    cfg: MCTSConfig,
) -> list[int]:
    """Return token indices the player can validly pick AFTER making
    `prior_picks` this env-turn.

    A token is valid iff:
      - It's the COMMIT sentinel (always valid; player can always stop), OR
      - Its source planet has enough ships left after subtracting the ship
        consumption of all prior picks from the same source.

    The returned list PRESERVES the ranking order from ``tokens`` (so PW
    can slice the top-k correctly). COMMIT appears in its ranked-list
    position — design §5.2 + cfg.commit_position determines whether that's
    the front (index 0) or the back (index len-1).

    The bucket-resolved ship count for a token uses the CURRENT post-prior
    pool, mirroring the serializer's logic exactly.
    """
    # Build the post-prior-picks ship pool
    ship_pool: dict[int, int] = {
        p.id: int(p.ships) for p in state.planets if p.owner == player_id
    }
    for prior_idx in prior_picks:
        if prior_idx >= len(tokens):
            continue
        prior_token = tokens[prior_idx]
        if prior_token.is_commit():
            continue
        avail = ship_pool.get(prior_token.src_planet_id, 0)
        if avail <= 0:
            continue
        fraction = cfg.ship_fraction_buckets[prior_token.ship_fraction_bucket]
        ships = max(1, int(avail * fraction))
        if ships > avail:
            ships = avail
        ship_pool[prior_token.src_planet_id] = max(0, avail - ships)

    # Walk tokens in ranking order, keeping COMMIT (always valid) and
    # launch tokens whose source can still afford the bucket-resolved ships.
    valid_indices: list[int] = []
    for idx, t in enumerate(tokens):
        if t.is_commit():
            valid_indices.append(idx)  # COMMIT always valid
            continue
        avail = ship_pool.get(t.src_planet_id, 0)
        if avail <= 0:
            continue
        fraction = cfg.ship_fraction_buckets[t.ship_fraction_bucket]
        ships = max(1, int(avail * fraction))
        if ships <= 0 or ships > avail:
            continue
        valid_indices.append(idx)
    return valid_indices


def _ucb_select_token(
    sub: SubNode,
    player_idx: int,
    considered_indices: list[int],
    cfg: MCTSConfig,
    fallback_idx: int = 0,
) -> int:
    """Pick the token_idx with the highest UCB1 + FPU score among
    ``considered_indices`` for ``player_idx`` at ``sub``.

    UCB exploration is computed against ``sub.visits`` (not the parent
    MCTSNode's visits) — sub-nodes have separate visit counts and the
    exploration term should reflect THIS sub-node's local statistics.

    ``fallback_idx`` is returned only if ``considered_indices`` is empty
    (defensive — filter_valid should always return at least COMMIT).
    """
    if not considered_indices:
        return fallback_idx
    if len(considered_indices) == 1:
        return considered_indices[0]

    parent_visits = sub.visits
    best_idx = considered_indices[0]
    best_score = -math.inf
    for token_idx in considered_indices:
        v, vsum = sub.get_stat(player_idx, token_idx)
        score = _ucb_score(v, vsum, parent_visits, cfg.ucb_c, cfg.fpu_c)
        if score > best_score:
            best_score = score
            best_idx = token_idx
    return best_idx


def _smmcts_token_iteration(
    node: TokenMCTSNode,
    sim: Simulator,
    cfg: MCTSConfig,
    alive_players: list[int],
    depth: int,
) -> dict[int, float]:
    """One SM-MCTS iteration in the token sub-tree architecture.

    Walks the per-env-turn launch sub-tree from root sub-node down to a
    sub-leaf (all committed OR cap hit), then either expands a new env-turn
    child or recurses into an existing one. Backprops through the sub-tree
    path AND through the env-turn ancestor.

    Returns per-player leaf values for backprop in the parent call.
    """
    # Terminal / depth limit (env-turn depth, not sub-tree depth)
    if depth >= cfg.max_depth or is_terminal(node.state):
        return {p: value_estimate(node.state, p) for p in alive_players}

    # Lazy ranking — only on first visit to this env-turn-state node
    for p in alive_players:
        if p not in node.ranked_tokens:
            node.ranked_tokens[p] = generate_ranked_tokens(node.state, p, cfg)

    # Walk down the sub-tree, recording the path for backprop
    sub = node.root_subnode(alive_players)
    path: list[tuple[SubNode, tuple[int, ...]]] = []  # (sub, joint_pick_indices)

    while True:
        # Termination: all committed → exit and descend
        if sub.all_committed:
            break
        # Termination: per-turn launch cap → forcibly commit all
        max_picks = max(len(p) for p in sub.picks_per_player) if sub.picks_per_player else 0
        if max_picks >= cfg.max_launches_per_turn:
            break

        # Build joint pick — one token_idx per alive player. For already-
        # committed players, the pick is just their commit_idx (no-op for
        # advancing state, but keeps the joint-pick tuple aligned).
        joint_pick: list[int] = []
        for p_idx, p in enumerate(alive_players):
            tokens = node.ranked_tokens[p]
            commit_idx = _find_commit_idx(tokens)
            if sub.committed_per_player[p_idx]:
                joint_pick.append(commit_idx)
                continue
            valid = _filter_valid_token_indices(
                tokens, sub.picks_per_player[p_idx], node.state, p, cfg
            )
            # Progressive Widening: limit to top-k by ranking position
            k = _pw_action_count(sub.visits, cfg)
            considered = valid[:min(k, len(valid))]
            chosen = _ucb_select_token(
                sub, p_idx, considered, cfg, fallback_idx=commit_idx,
            )
            joint_pick.append(chosen)
        joint_pick_t = tuple(joint_pick)

        path.append((sub, joint_pick_t))

        # Compute next sub-node key. Picking COMMIT marks the player as
        # committed; picking a launch token appends to picks_per_player.
        new_picks = []
        new_committed = []
        for i, idx in enumerate(joint_pick):
            tokens_i = node.ranked_tokens[alive_players[i]]
            picked_token = tokens_i[idx] if idx < len(tokens_i) else None
            if picked_token is None or picked_token.is_commit():
                new_picks.append(sub.picks_per_player[i])
                new_committed.append(True)
            else:
                new_picks.append(sub.picks_per_player[i] + (idx,))
                new_committed.append(sub.committed_per_player[i])
        new_picks_t = tuple(new_picks)
        new_committed_t = tuple(new_committed)
        next_key = make_subnode_key(new_picks_t, new_committed_t)
        next_sub = node.subnode_cache.get(next_key)
        if next_sub is None:
            next_sub = SubNode(new_picks_t, new_committed_t)
            node.subnode_cache[next_key] = next_sub
        sub = next_sub

    # Sub-leaf reached. Build the env-turn child key from accumulated picks.
    committed_key = canonicalize_committed(sub.picks_per_player)

    if committed_key not in node.children:
        # Expansion: serialize, simulate, evaluate
        picks_dict: dict[int, list[int]] = {
            p: list(sub.picks_per_player[i]) for i, p in enumerate(alive_players)
        }
        env_actions_typed = serialize_picks_to_env_actions(
            picks_dict, node.ranked_tokens, node.state, cfg
        )
        next_state = sim.step(node.state, env_actions_typed)
        child = TokenMCTSNode(state=next_state)
        node.children[committed_key] = child
        leaf_values = {p: value_estimate(next_state, p) for p in alive_players}
    else:
        # Recurse into existing child. Alive set may change due to eliminations.
        child = node.children[committed_key]
        child_alive = sorted(child.state.alive_players())
        leaf_values = _smmcts_token_iteration(
            child, sim, cfg, child_alive, depth + 1
        )

    # Backprop along the sub-tree path: every visited sub-node updates the
    # stat for the pick it made, and increments its visit count.
    for sub_visited, joint in path:
        sub_visited.visits += 1
        for p_idx, token_idx in enumerate(joint):
            p = alive_players[p_idx]
            v = leaf_values.get(p, 0.0)
            sub_visited.update_stat(p_idx, token_idx, v)

    # The leaf sub-node also gets a visit (no stats update — no pick was made
    # FROM it; we left via the env-turn child).
    sub.visits += 1
    node.visits += 1
    return leaf_values


def _search_tokens(
    state: SimState,
    cfg: MCTSConfig,
    our_player: int,
    *,
    deadline_s: float | None = None,
) -> tuple[ActionList, dict]:
    """Option-2 single-launch-token sub-tree SM-MCTS search.

    Builds a TokenMCTSNode root, pre-populates ranked tokens for all alive
    players, runs ``_smmcts_token_iteration`` until the deadline, then picks
    OUR player's action from the most-visited COMMITTED CHILD (per design
    §6.4 + open Q1 default).

    Returns (action_list_in_env_format, debug_dict).
    """
    sim = Simulator()
    root = TokenMCTSNode(state=state)
    alive = sorted(state.alive_players())
    started = time.perf_counter()
    if deadline_s is None:
        deadline_s = started + cfg.turn_budget_ms / 1000.0

    # Pre-populate ranked tokens at root for all alive players
    for p in alive:
        root.ranked_tokens[p] = generate_ranked_tokens(state, p, cfg)

    iterations = 0
    while time.perf_counter() < deadline_s:
        _smmcts_token_iteration(root, sim, cfg, alive, depth=0)
        iterations += 1

    # Robust child: most-visited COMMITTED CHILD at root.
    if not root.children:
        # Out of time before any iteration completed — fall back to heuristic.
        # The agent.py wrapper will catch this via fallback_threshold_ms in
        # most cases; this is the belt-and-braces.
        return [], {
            "iterations": iterations,
            "fallback": "no_committed_children",
            "elapsed_s": time.perf_counter() - started,
        }

    best_committed_key = max(
        root.children.keys(), key=lambda k: root.children[k].visits
    )
    best_child_visits = root.children[best_committed_key].visits

    # Extract OUR player's pick sequence from the committed key
    our_idx = alive.index(our_player) if our_player in alive else 0
    our_pick_indices = best_committed_key[our_idx] if our_idx < len(best_committed_key) else ()

    # Serialize OUR player's picks back to env actions (the dict shape allows
    # other players to be present too — we only need ours)
    picks: dict[int, list[int]] = {our_player: list(our_pick_indices)}
    actions_per_player = serialize_picks_to_env_actions(
        picks, root.ranked_tokens, state, cfg
    )
    chosen: ActionList = [
        a.to_env_format() for a in actions_per_player.get(our_player, [])
    ]

    debug = {
        "iterations": iterations,
        "root_visits": root.visits,
        "n_children": len(root.children),
        "best_child_visits": best_child_visits,
        "our_pick_count": len(our_pick_indices),
        "our_token_indices": list(our_pick_indices),
        "elapsed_s": time.perf_counter() - started,
    }
    return chosen, debug
