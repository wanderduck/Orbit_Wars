"""MCTS forward-model simulator + validation harness.

This package builds out the env-faithful forward model that MCTS rollouts
depend on. See `docs/research_documents/mcts_forward_model_design.md`.

Build order (Day 14 hard kill-switch):
- Days 1-2: scenario extractor (validator.collect_scenarios)
- Days 3-5: minimal simulator (phases 2, 3, 6) + initial validate()
- Days 5-7: phase 4 (fleet movement)
- Days 7-9: phase 5 (rotation + sweep)
- Days 9-11: phase 0 (comet expiration), comet handling end-to-end
- Day 14 GATE: ≥99% match across 1000+ random scenarios
- Days 14-16: profile + Numba pass on hot path (design doc Section 6)
- Days 16+: MCTS algorithm (separate doc)
"""

from .action import Action, validate_move
from .simulator import Simulator
from .state import (
    SimCometGroup,
    SimConfig,
    SimFleet,
    SimPlanet,
    SimState,
)
from .validator import (
    ForwardModelValidator,
    ValidationReport,
    ValidationTriple,
)

__all__ = [
    "Action",
    "ForwardModelValidator",
    "SimCometGroup",
    "SimConfig",
    "SimFleet",
    "SimPlanet",
    "SimState",
    "Simulator",
    "ValidationReport",
    "ValidationTriple",
    "validate_move",
]
