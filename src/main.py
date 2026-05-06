"""Orbit Wars Kaggle submission entry point.

The ``agent`` function is imported by the Kaggle harness and called once per
turn. Routes through ``orbit_wars.mcts.mcts_agent`` which, when
``MCTSConfig.enabled=False`` (Phase M1 default), transparently delegates to
the heuristic at ``orbit_wars.heuristic.strategy.agent``.

Toggle MCTS by editing ``MCTS_CFG.enabled`` here. Phase M1 ships this
wrapper with enabled=False to validate plumbing — the ladder μ should not
move from the heuristic baseline. Subsequent phases (M2+) add the actual
SM-MCTS search behind the same toggle.
"""

from orbit_wars.mcts import MCTSConfig, mcts_agent

# Module-level config. Edit `enabled` to switch between heuristic-only
# (M1 baseline) and MCTS (M2+ once implemented). Frozen dataclass keeps
# this safe against accidental per-turn mutation.
MCTS_CFG = MCTSConfig(enabled=False)


def agent(obs, config=None):
    """Kaggle entry point. See ``mcts_agent`` docstring for details."""
    return mcts_agent(obs, MCTS_CFG)


__all__ = ["agent", "MCTS_CFG"]
