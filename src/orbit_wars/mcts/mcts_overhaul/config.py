"""MCTS Overhaul configuration dataclass for NN-guided token search."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MCTSOverhaulConfig:
    """Configuration for the stripped-down, NN-guided MCTS agent.
    Option 1 (legacy compound variants) has been removed.
    """

    # Master toggle.
    enabled: bool = False

    # ---- NN & Path Settings ----
    onnx_model_path: str = ""  # Path to the ONNX model for CPU inference. If empty, falls back to heuristic.
    nn_batch_size: int = 1     # Batch size for ONNX inference (1 is typical for synchronous MCTS)
    
    # ---- Search structure ----
    # Progressive Widening: at a node with n visits for player p, consider
    # k_p = ceil(WIDEN_C * n^WIDEN_ALPHA) actions.
    widen_c: float = 2.0
    widen_alpha: float = 0.5

    # First-Play Urgency
    fpu_c: float = 0.5

    # UCB1 exploration constant.
    ucb_c: float = math.sqrt(2.0)

    # Tree depth limit (lookahead horizon in env turns).
    max_depth: int = 5

    # ---- Time budget ----
    turn_budget_ms: float = 700.0
    fallback_threshold_ms: float = 50.0
    max_iteration_ms: float = 25.0

    # ---- Token Search Parameters ----
    ship_fraction_buckets: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0)
    
    # Number of fraction-bucket tokens emitted per LaunchDecision in the prior.
    tokens_per_decision: int = 3

    # Per-env-turn sub-tree depth cap.
    max_launches_per_turn: int = 4

    # Where to place the COMMIT_TURN sentinel.
    commit_position: str = "last"
