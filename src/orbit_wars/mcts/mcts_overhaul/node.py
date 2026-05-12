"""MCTS Node definition for PUCT Search."""
from __future__ import annotations

class Node:
    __slots__ = ['state', 'accumulated_tokens', 'visits', 'value_sum', 'prior', 'children']

    def __init__(self, state=None, accumulated_tokens=None, prior: float = 0.0):
        self.state = state
        self.accumulated_tokens = accumulated_tokens or []
        self.visits = 0
        self.value_sum = 0.0
        self.prior = prior
        self.children: dict[int, Node] | None = None