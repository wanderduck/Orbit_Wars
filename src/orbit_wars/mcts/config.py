"""MCTS configuration dataclass.

Constants per design doc v2 §3.5 (
docs/research_documents/2026-05-06-mcts-algorithm-design.md). All values are
initial; M3 will tune via local A/B testing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MCTSConfig:
    """All knobs for the MCTS agent. Frozen so it can be safely shared
    across the agent's stateless calls.

    Phase M1 only uses ``enabled``. M2 adds the per-iteration search
    constants. M3 tunes them.
    """

    # Master toggle. False = pure heuristic (null-MCTS baseline).
    enabled: bool = False

    # ---- Search structure (used from M2 onward) ----

    # Progressive Widening: at a node with n visits for player p, consider
    # k_p = ceil(WIDEN_C * n^WIDEN_ALPHA) actions, sorted by heuristic.
    widen_c: float = 2.0
    widen_alpha: float = 0.5

    # First-Play Urgency: UCB value assigned to unvisited actions instead
    # of +inf. 0.5 is "we don't know — assume average".
    fpu_c: float = 0.5

    # UCB1 exploration constant.
    ucb_c: float = math.sqrt(2.0)

    # Tree depth limit (lookahead horizon).
    max_depth: int = 5

    # ---- Time budget (used from M2 onward) ----

    # Total wall clock budget per agent decision, in milliseconds.
    # Kaggle actTimeout is 1000ms; reserve 300ms safety margin.
    turn_budget_ms: float = 700.0

    # Fall back to heuristic if remaining budget < this after state extraction
    # and root setup. Avoids the "started one bad iteration with 5ms left" trap.
    fallback_threshold_ms: float = 50.0

    # Soft per-iteration ceiling. The simulator step is ~1.77ms, heuristic
    # eval is ~5ms; budget for a deep iteration with expansion is ~25ms.
    max_iteration_ms: float = 25.0

    # ---- Phase M2+ knobs (initial values) ----

    # Number of actions to consider per player WHEN PW IS DISABLED (M2 only).
    # Replaced by widen_c/widen_alpha in M3.
    fixed_k_per_player: int = 8

    # Ship-fraction discretization for action tokens.
    # Maps an "amount of ships" choice into discrete buckets so PW has a
    # finite action space to rank. M2 default; tunable in M3.
    ship_fraction_buckets: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0)
