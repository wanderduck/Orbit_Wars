"""MCTS agent entry point for Kaggle."""
from __future__ import annotations
import time
from typing import Any

from .config import MCTSOverhaulConfig
from orbit_wars.heuristic.heuristic_overhaul.strategy import agent as heuristic_agent
from orbit_wars.state import ObservationView
from orbit_wars.mcts.extract import extract_state_from_obs, infer_num_agents_from_obs

# Module-level config.
MCTS_CFG = MCTSOverhaulConfig(enabled=True, onnx_model_path="models/mcts_net.onnx")

# Global ONNX model lazy loading
_evaluator = None

def _get_evaluator(path: str):
    global _evaluator
    if _evaluator is None and path:
        try:
            from .nn_model import ONNXEvaluator
            _evaluator = ONNXEvaluator(path)
        except Exception as e:
            print(f"Failed to load ONNX model: {e}")
            _evaluator = False # mark as failed
    return _evaluator if _evaluator is not False else None

def agent(obs: Any, config: Any = None) -> list[list[float | int]]:
    cfg = config if isinstance(config, MCTSOverhaulConfig) else MCTS_CFG
    
    if not cfg.enabled:
        return heuristic_agent(obs, None)
        
    started = time.perf_counter()
    try:
        num_agents = infer_num_agents_from_obs(obs)
        state = extract_state_from_obs(obs, num_agents=num_agents)
        our_player = int(getattr(obs, "player", 0)) if hasattr(obs, "player") and getattr(obs, "player", None) is not None else int(getattr(obs, "get", lambda k, d: d)("player", 0))
        
        evaluator = _get_evaluator(cfg.onnx_model_path)
        if evaluator is None:
            return heuristic_agent(obs, None)
            
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        remaining_ms = max(cfg.turn_budget_ms - elapsed_ms, 0.0)
        
        if remaining_ms < cfg.fallback_threshold_ms:
            return heuristic_agent(obs, None)
            
        deadline_s = time.perf_counter() + remaining_ms / 1000.0
        
        from .search import search
        return search(state, cfg, our_player, evaluator, deadline_s=deadline_s)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return heuristic_agent(obs, None)
