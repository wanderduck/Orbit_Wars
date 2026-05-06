"""MCTS agent entrypoint.

Phase M1 (skeleton): when ``MCTSConfig.enabled`` is False, this function
transparently delegates to the heuristic agent. This is the no-regression
baseline — the wrapper itself adds no behavior change so any ladder μ delta
in M1 is a wrapper bug, not an MCTS effect.

Phase M2 will add the actual SM-MCTS loop here. The signature is fixed
across phases so toggling `enabled` is the only way to compare.

Critical preserved env quirks (per CLAUDE.md "Agent architecture"):
- ``obs`` may be a dict OR a Struct → delegated to heuristic which handles both.
- The ``config`` second positional arg trap: kaggle_environments passes its
  env-config Struct as the second positional arg. We MUST guard against
  treating that as our MCTSConfig. The fix is the same as the heuristic's:
  isinstance check before using it as our config.
- Always-safe heuristic fallback on any exception. The agent must never
  return invalid output to env even if MCTS code crashes.
"""

from __future__ import annotations

from typing import Any

from .config import MCTSConfig

# Module-level default config. Mutated only at startup by env-tuning logic.
# Frozen dataclass keeps it safe against accidental mutation per turn.
_DEFAULT_CFG = MCTSConfig()


def mcts_agent(
    obs: Any,
    config: Any = None,
    *,
    fallback_to_heuristic: bool = True,
) -> list[list[float | int]]:
    """Decide one turn's actions for player 0.

    Args:
        obs: Kaggle observation (dict or Struct).
        config: Either a ``MCTSConfig`` instance or the env-config Struct
            that kaggle_environments passes positionally. Only honored if
            it's actually an ``MCTSConfig``; otherwise falls back to the
            module default. (This guard mirrors the env-positional-arg
            trap documented in CLAUDE.md.)
        fallback_to_heuristic: If True, any exception or disabled MCTS
            falls through to the heuristic agent. Set False only in tests
            where you want the exception to surface.

    Returns:
        list of moves, each move shaped ``[from_planet_id, angle, ships]``.
    """
    # Late import: keeps import-time cycles avoided and makes mcts_agent
    # cheap to import for tests that don't actually call it.
    from orbit_wars.heuristic.strategy import agent as heuristic_agent

    # Resolve config: only trust an actual MCTSConfig instance.
    cfg = config if isinstance(config, MCTSConfig) else _DEFAULT_CFG

    # Phase M1: when disabled, delegate transparently. This is the
    # no-regression baseline.
    if not cfg.enabled:
        return heuristic_agent(obs, None)

    # Phase M2+ will land the actual SM-MCTS search here. For now,
    # enabled=True is just a fallback to heuristic with a debug print
    # so it's obvious in logs that MCTS is "enabled but not implemented".
    if not fallback_to_heuristic:
        raise NotImplementedError("MCTS phase M2+ not yet implemented")
    # Defensive: enabled=True but no implementation → heuristic.
    return heuristic_agent(obs, None)
