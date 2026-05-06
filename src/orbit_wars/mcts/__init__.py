"""MCTS algorithm for Orbit Wars.

See `docs/research_documents/2026-05-06-mcts-algorithm-design.md` for the
full design (v2 — SM-MCTS + Progressive Widening + FPU per Aljabasini 2021).

Phase M1 (skeleton): just exposes MCTSConfig + mcts_agent that, when
disabled, transparently delegates to the heuristic agent. Future phases
M2-M5 grow the actual MCTS search.

Usage:
    from orbit_wars.mcts import mcts_agent, MCTSConfig
    cfg = MCTSConfig(enabled=False)        # null-MCTS — uses heuristic
    action = mcts_agent(obs, cfg)
"""

from .agent import mcts_agent
from .config import MCTSConfig

__all__ = ["MCTSConfig", "mcts_agent"]
