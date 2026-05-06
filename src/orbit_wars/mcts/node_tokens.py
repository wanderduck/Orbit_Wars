"""SubNode + token-aware MCTSNode for the option-2 sub-tree-per-env-turn design.

Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md §4.2.

Architecture summary (read this before touching the code):

  Each ``MCTSNode`` represents one ENV-TURN STATE. Inside that node lives a
  per-env-turn launch SUB-TREE — a tree of ``SubNode`` objects keyed by
  "what tokens has each player picked SO FAR this env-turn". When all alive
  players have selected COMMIT (or the per-turn cap is hit), the sub-tree
  reaches a leaf, the simulator advances ONE env turn, and the resulting
  state becomes a CHILD MCTSNode (next env-turn).

  Per-player UCB stats live AT THE SUB-NODE level (not at the MCTSNode
  level as in the legacy compound-variant search). Each sub-node tracks
  per-player {token_idx: [visits, value_sum]} for the next pick.

Key types:
  JointCommit -- the canonical key identifying a fully-committed joint pick set.
                 ORDER-PRESERVING tuple-of-tuples; do NOT use frozensets.
                 Reason: env action processing is order-dependent (later picks
                 from the same source planet see a reduced ship pool, so
                 ordering changes ship counts and thus next-state).

DEVIATIONS from the design doc:
  - JointCommit uses tuple[tuple[int, ...], ...] (ordered) instead of
    tuple[frozenset[int], ...] (set). See above.
  - The legacy MCTSNode in node.py is unchanged. This module is the new
    implementation, dispatched via cfg.use_token_variants.

The sub-tree walking logic itself (UCB selection at sub-step, expansion,
backprop) lives in search.py:_search_tokens, NOT here. This module is
just the data structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orbit_wars.sim.state import SimState

from .token import LaunchToken

__all__ = [
    "JointCommit",
    "MCTSNode",
    "SubNode",
    "SubNodeKey",
    "canonicalize_committed",
    "make_subnode_key",
]


# Identity for one node within the per-env-turn sub-tree.
# (picks_per_player, committed_per_player) — both index-aligned to alive
# players sorted by player_id.
SubNodeKey = tuple[tuple[tuple[int, ...], ...], tuple[bool, ...]]

# Identity for a child MCTSNode under a parent. The committed picks (in pick
# order) for each alive player, sorted by player_id index. Order-preserving
# because env step is order-sensitive (see module docstring).
JointCommit = tuple[tuple[int, ...], ...]


@dataclass(slots=True)
class SubNode:
    """One node in the per-env-turn launch sub-tree.

    Identity is (``picks_per_player``, ``committed_per_player``):
      - ``picks_per_player[i]``: ordered tuple of token_idx values that
        alive-player[i] has chosen during this env-turn.
      - ``committed_per_player[i]``: True iff alive-player[i] has selected
        COMMIT (no more picks from them this env-turn).

    Per-player UCB stats live HERE — ``stats[player_idx][token_idx]`` =
    ``[visits, value_sum]`` for the pick made FROM THIS sub-node by that
    player. Sub-step UCB selection in search.py reads from these stats.

    The mapping uses player_idx (the position in the sorted alive_players
    list), not raw player_id, because the players list can shrink between
    env-turns (eliminated players drop out) but the indexing within one
    env-turn is fixed.
    """

    picks_per_player: tuple[tuple[int, ...], ...]
    committed_per_player: tuple[bool, ...]
    stats: dict[int, dict[int, list[float]]] = field(default_factory=dict)
    visits: int = 0

    def get_stat(self, player_idx: int, token_idx: int) -> tuple[int, float]:
        """Return (visits, value_sum) for ``token_idx`` if picked by
        ``player_idx`` from this sub-node, else (0, 0.0)."""
        pstats = self.stats.get(player_idx)
        if pstats is None:
            return 0, 0.0
        s = pstats.get(token_idx)
        if s is None:
            return 0, 0.0
        return int(s[0]), float(s[1])

    def update_stat(self, player_idx: int, token_idx: int, value: float) -> None:
        """Increment visits + value_sum for the (player_idx, token_idx) pick."""
        pstats = self.stats.setdefault(player_idx, {})
        s = pstats.setdefault(token_idx, [0.0, 0.0])
        s[0] += 1.0
        s[1] += float(value)

    @property
    def all_committed(self) -> bool:
        """True iff every alive-player slot has committed."""
        return all(self.committed_per_player)


def make_subnode_key(
    picks_per_player: tuple[tuple[int, ...], ...],
    committed_per_player: tuple[bool, ...],
) -> SubNodeKey:
    """Canonical hashable key for a sub-node. Both inputs must already be
    tuples (immutable) for hashability. This wrapper exists for clarity and
    to standardize the type used for the cache dict."""
    return (picks_per_player, committed_per_player)


def canonicalize_committed(picks_per_player: tuple[tuple[int, ...], ...]) -> JointCommit:
    """Build the order-PRESERVING key for the env-turn child MCTSNode.

    See module docstring: env action processing is order-sensitive, so we
    cannot use frozensets here. Two different orderings of the same picks
    yield (potentially) different next-states; they must be separate child
    MCTSNodes.
    """
    return picks_per_player


@dataclass(slots=True)
class MCTSNode:
    """One env-turn state. Owns its per-env-turn launch sub-tree.

    NOT compatible with the legacy MCTSNode in ``node.py`` — the legacy node
    has per-(player, action_idx) stats AT the env-turn level, while this
    node has those stats AT the SUB-NODE level (since per-env-turn picks
    span multiple sub-steps).

    Lifecycle:
      1. Constructed at expansion with a SimState.
      2. On first visit, ``ranked_tokens[p]`` is populated for each alive
         player via ``tokens.generate_ranked_tokens`` (lazy — keeps cost
         out of nodes that get visited rarely).
      3. SM-MCTS iterations walk the sub-tree (subnode_cache), expand
         sub-nodes on demand. Each iteration ends at a sub-leaf (all
         committed or cap hit).
      4. From the sub-leaf, the joint COMMIT key is built and looked up
         in ``children``. Cache miss → call simulator.step + create child
         MCTSNode. Cache hit → recurse into existing child.

    The same MCTSNode is re-visited many times across a search. Its
    sub-tree GROWS in place each iteration.
    """

    state: SimState
    visits: int = 0
    # Per-player ranked tokens at THIS env-turn-state. Computed once on
    # first visit (per-player). Indexed 0..N-1 with index 0 == COMMIT.
    ranked_tokens: dict[int, list[LaunchToken]] = field(default_factory=dict)
    # Sub-tree cache. Key = SubNodeKey. Always contains the root sub-node
    # (empty picks, no commits) once root_subnode() is first called.
    subnode_cache: dict[SubNodeKey, SubNode] = field(default_factory=dict)
    # Env-turn children, keyed by the JointCommit (committed picks per player).
    # Populated lazily on sub-leaf expansion via simulator.step.
    children: dict[JointCommit, "MCTSNode"] = field(default_factory=dict)

    def root_subnode(self, alive_players: list[int]) -> SubNode:
        """Get or lazily create the root sub-node (no picks, no commits).

        ``alive_players`` is the index-aligned ordering used throughout the
        sub-tree for THIS env-turn. The caller is responsible for keeping it
        consistent (e.g., always ``sorted(state.alive_players())``).
        """
        empty_picks: tuple[tuple[int, ...], ...] = tuple(() for _ in alive_players)
        empty_committed: tuple[bool, ...] = tuple(False for _ in alive_players)
        key = make_subnode_key(empty_picks, empty_committed)
        sub = self.subnode_cache.get(key)
        if sub is None:
            sub = SubNode(empty_picks, empty_committed)
            self.subnode_cache[key] = sub
        return sub
