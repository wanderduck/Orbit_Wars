"""Overhauled SM-MCTS using ONNX Neural Network for priors and values."""
from __future__ import annotations
import math
import time
import numpy as np

from orbit_wars.sim.simulator import Simulator
from orbit_wars.mcts.serialize import serialize_picks_to_env_actions
from .node import Node
from .features import extract_features_sim
from .dense_token_adjusted import decode_dense_token, NUM_TOKENS

def softmax(x):
    y = x - np.max(x)
    np.exp(y, out=y)
    return y / np.sum(y)

def search(state, cfg, our_player, evaluator, deadline_s):
    root = Node(state=state, accumulated_tokens=[])
    sim = Simulator()

    while time.perf_counter() < deadline_s:
        _simulate(root, sim, our_player, evaluator, cfg, depth=0)

    if not root.children:
        return []

    curr = root
    my_tokens = []

    while curr.children:
        best_idx = max(curr.children.keys(), key=lambda k: curr.children[k].visits)
        token = decode_dense_token(best_idx)
        if token.is_commit():
            break
        my_tokens.append(token)
        curr = curr.children[best_idx]
        if len(my_tokens) >= cfg.max_launches_per_turn:
            break

    picks_dict = {our_player: list(range(len(my_tokens)))}
    ranked_tokens = {our_player: my_tokens}

    actions_per_player = serialize_picks_to_env_actions(picks_dict, ranked_tokens, state, cfg)
    return [a.to_env_format() for a in actions_per_player.get(our_player, [])]

def _simulate(node, sim, our_player, evaluator, cfg, depth):
    if depth >= cfg.max_depth:
        if node.visits == 0:
            features = extract_features_sim(node.state, our_player, node.accumulated_tokens)
            _, val = evaluator.evaluate(features)
            return val
        return node.value_sum / node.visits

    if node.children is None:
        features = extract_features_sim(node.state, our_player, node.accumulated_tokens)
        pol, val = evaluator.evaluate(features)

        probs = softmax(pol)
        node.children = {}

        K = min(32, NUM_TOKENS)

        # O(N) Partitions are radically faster than O(N log N) sorts
        if len(probs) > K:
            top_indices = np.argpartition(probs, -K)[-K:]
        else:
            top_indices = np.arange(len(probs))

        for idx in top_indices:
            node.children[int(idx)] = Node(state=None, prior=float(probs[idx]))

        return val

    best_score = -float('inf')
    best_idx = -1

    sqrt_visits = math.sqrt(node.visits)
    for idx, child in node.children.items():
        q = child.value_sum / child.visits if child.visits > 0 else cfg.fpu_c
        u = cfg.ucb_c * child.prior * sqrt_visits / (1 + child.visits)
        score = q + u
        if score > best_score:
            best_score = score
            best_idx = idx

    child = node.children[best_idx]

    if child.state is None:
        token = decode_dense_token(best_idx)

        # We only advance the environment turn tick if COMMIT is chosen
        if token.is_commit() or len(node.accumulated_tokens) >= cfg.max_launches_per_turn:
            my_tokens = list(node.accumulated_tokens)
            if not token.is_commit():
                my_tokens.append(token)

            picks_dict = {our_player: list(range(len(my_tokens)))}
            ranked_tokens = {our_player: my_tokens}
            actions_per_player = serialize_picks_to_env_actions(picks_dict, ranked_tokens, node.state, cfg)

            child.state = sim.step(node.state, actions_per_player)
            child.accumulated_tokens = []
        else:
            child.state = node.state
            child.accumulated_tokens = node.accumulated_tokens + [token]

    val = _simulate(child, sim, our_player, evaluator, cfg, depth + 1)

    node.visits += 1
    node.value_sum += val
    return val