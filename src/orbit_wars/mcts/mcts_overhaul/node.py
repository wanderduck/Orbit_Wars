"""MCTS Node definition for PUCT Search."""
from __future__ import annotations

class Node:
    __slots__ = ['state', 'visits', 'value_sum', 'prior', 'children']
    
    def __init__(self, state=None, prior: float = 0.0):
        self.state = state
        self.visits = 0
        self.value_sum = 0.0
        self.prior = prior
        self.children: dict[int, Node] | None = None
