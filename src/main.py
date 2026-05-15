"""Orbit Wars Kaggle submission entry point.

Uses the MCTS Overhaul with the trained ONNX model.
"""
from orbit_wars.mcts.mcts_overhaul.agent import agent as mcts_agent

def agent(obs, config=None):
    """Kaggle entry point using MCTS Overhaul."""
    return mcts_agent(obs, config)

__all__ = ["agent"]