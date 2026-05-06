"""MCTSNode — per-node statistics for SM-MCTS with decoupled UCT.

Each node holds:
  - The simulator state (for child generation when expanded)
  - Per-player ranked candidate actions (lazily filled on first visit)
  - Per-player UCB stats: action_index → (visits, value_sum)
  - Children indexed by joint action (tuple of action_index per player)

In decoupled UCT, each player picks their own action argmax UCB
INDEPENDENTLY at each node. The joint tuple drives the simulator.step()
call, and the resulting next state is the child node.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orbit_wars.sim.state import SimState

from .ranking import ActionList


# A joint action is a tuple of action-indices, sorted by player_id.
# E.g. for 2P with our pick=3 and opp pick=0, joint = (3, 0).
JointAction = tuple[int, ...]


@dataclass(slots=True)
class MCTSNode:
    """One node in the SM-MCTS tree.

    Lazy initialization: ranked_actions and stats start empty and get
    populated the first time a player needs to act at this node.
    """

    state: SimState
    # Total number of times this node has been visited (sum across players).
    visits: int = 0
    # Per-player ranked candidate actions. player_id -> list of compound
    # action lists, indexed 0..K-1 by descending priority.
    ranked_actions: dict[int, list[ActionList]] = field(default_factory=dict)
    # Per-player UCB stats: player_id -> {action_idx: [visits, value_sum]}
    # Use list (not tuple) for in-place mutation.
    stats: dict[int, dict[int, list[float]]] = field(default_factory=dict)
    # Children indexed by JointAction tuple. Populated lazily on expansion.
    children: dict[JointAction, "MCTSNode"] = field(default_factory=dict)

    def get_ranked(
        self, player_id: int, ranker, k: int
    ) -> list[ActionList]:
        """Return cached ranked actions for `player_id`; populate if absent."""
        cached = self.ranked_actions.get(player_id)
        if cached is None:
            cached = ranker(self.state, player_id, k=k)
            self.ranked_actions[player_id] = cached
        return cached

    def get_stat(self, player_id: int, action_idx: int) -> tuple[int, float]:
        """Return (visits, value_sum) for a given (player, action). Default 0/0."""
        pstats = self.stats.get(player_id)
        if pstats is None:
            return 0, 0.0
        s = pstats.get(action_idx)
        if s is None:
            return 0, 0.0
        return int(s[0]), float(s[1])

    def update_stat(
        self, player_id: int, action_idx: int, value: float
    ) -> None:
        """Increment visits and add value for (player, action). Used in backprop."""
        pstats = self.stats.setdefault(player_id, {})
        s = pstats.setdefault(action_idx, [0.0, 0.0])
        s[0] += 1
        s[1] += value
