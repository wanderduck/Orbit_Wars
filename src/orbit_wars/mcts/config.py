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

    # ---- Option 2 (single-launch token action space) knobs ----
    # Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md.
    #
    # Compound-variant search (use_token_variants=False) is the legacy /
    # M3 path: each MCTS step picks one full action list. Token search
    # (use_token_variants=True) is the canonical SM-MCTS path: each MCTS
    # sub-step picks one launch token, multiple launches per env-turn are
    # composed via per-env-turn launch sub-trees, simulator advances when
    # both players COMMIT (or hit max_launches_per_turn cap).

    # Master toggle for option-2 architecture. Default False so M3 baseline
    # remains the no-regression path until option 2 passes its local A/B gate.
    use_token_variants: bool = False

    # Number of fraction-bucket tokens emitted per LaunchDecision in the prior.
    # Per design §4.5: chosen-bucket + (tokens_per_decision-1) nearest. Higher =
    # richer prior but more cost to rank; default 3 = chosen + 2 neighbors.
    tokens_per_decision: int = 3

    # Per-env-turn sub-tree depth cap. Per design §3.2.2: bounds sub-tree size at
    # (PW_k+1)^cap worst case. 4 ≈ heuristic's median per-turn launch count.
    max_launches_per_turn: int = 4

    # Whether to extend ranked_tokens with the long-tail (~530 src×target×bucket
    # tokens). Default OFF per Risk 1 mitigation: enable selectively if M5 perf
    # data shows long-tail matters in practice.
    long_tail_enabled: bool = False
