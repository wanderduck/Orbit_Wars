"""MCTS Overhaul configuration dataclass for NN-guided token search."""
from __future__ import annotations
import math
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class MCTSOverhaulConfig:
    enabled: bool = False
    onnx_model_path: str = ""
    nn_batch_size: int = 1

    widen_c: float = 2.05
    widen_alpha: float = 0.55
    fpu_c: float = 0.1
    ucb_c: float = 1.69

    # Can expand this significantly deeper due to O(N) loop optimizations
    max_depth: int = 13

    turn_budget_ms: float = 777.0
    fallback_threshold_ms: float = 123.0
    max_iteration_ms: float = 69.0

    ship_fraction_buckets: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8, 1.0)
    tokens_per_decision: int = 3
    max_launches_per_turn: int = 5
    commit_position: str = "last"