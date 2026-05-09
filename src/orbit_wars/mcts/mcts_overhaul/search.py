"""Overhauled SM-MCTS using ONNX Neural Network for priors and values."""

from __future__ import annotations
import math
import time
import numpy as np

from orbit_wars.sim.simulator import Simulator
from orbit_wars.mcts.serialize import serialize_picks_to_env_actions

from .node import Node
from .features import extract_features_sim
from .dense_token import decode_dense_token, NUM_TOKENS

def softmax(x):
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()

def search(state, cfg, our_player, evaluator, deadline_s):
    """Main search loop using PUCT algorithm guided by Neural Network."""
    root = Node(state=state)
    sim = Simulator()
    
    iterations = 0
    while time.perf_counter() < deadline_s:
        _simulate(root, sim, our_player, evaluator, cfg, depth=0)
        iterations += 1
        
    if not root.children:
        return []
        
    # Extract the best sequence of actions
    curr = root
    picks = []
    while curr.children:
        best_idx = max(curr.children.keys(), key=lambda k: curr.children[k].visits)
        token = decode_dense_token(best_idx)
        if token.is_commit():
            break
        picks.append(best_idx)
        curr = curr.children[best_idx]
        
    my_tokens = [decode_dense_token(idx) for idx in picks]
    picks_dict = {our_player: list(range(len(my_tokens)))}
    ranked_tokens = {our_player: my_tokens}
    
    actions_per_player = serialize_picks_to_env_actions(picks_dict, ranked_tokens, state, cfg)
    chosen = [a.to_env_format() for a in actions_per_player.get(our_player, [])]
    return chosen

def _simulate(node, sim, our_player, evaluator, cfg, depth):
    if depth >= cfg.max_depth:
        return 0.0 # Leaf cutoff, assume 0 for neutral or use heuristic value
        
    if node.children is None:
        # Expand
        features = extract_features_sim(node.state, our_player)
        pol, val = evaluator.evaluate(features)
        
        # Apply softmax to policy
        probs = softmax(pol)
        
        node.children = {}
        # Expand top K tokens to save CPU cycles
        K = min(16, NUM_TOKENS)
        top_indices = np.argsort(probs)[-K:]
        
        for idx in top_indices:
            node.children[int(idx)] = Node(state=None, prior=float(probs[idx]))
            
        return val
        
    # Select
    best_score = -float('inf')
    best_idx = -1
    
    for idx, child in node.children.items():
        q = child.value_sum / child.visits if child.visits > 0 else 0.0
        u = cfg.ucb_c * child.prior * math.sqrt(node.visits) / (1 + child.visits)
        score = q + u
        if score > best_score:
            best_score = score
            best_idx = idx
            
    child = node.children[best_idx]
    
    if child.state is None:
        # Transition state using the token
        token = decode_dense_token(best_idx)
        if token.is_commit():
            child.state = sim.step(node.state, {})
        else:
            my_tokens = [token]
            picks_dict = {our_player: [0]}
            ranked_tokens = {our_player: my_tokens}
            actions_per_player = serialize_picks_to_env_actions(picks_dict, ranked_tokens, node.state, cfg)
            
            child.state = sim.step(node.state, actions_per_player)
            
    val = _simulate(child, sim, our_player, evaluator, cfg, depth + 1)
    
    node.visits += 1
    node.value_sum += val
    return val
