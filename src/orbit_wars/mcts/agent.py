"""MCTS agent entrypoint.

Phase M1 (skeleton): when ``MCTSConfig.enabled`` is False, this function
transparently delegates to the heuristic agent. The no-regression baseline
that validates plumbing — any ladder μ delta is a wrapper bug.

Phase M2 (this file's current state): when ``enabled=True``, runs bare
SM-MCTS (decoupled UCT, fixed k per player, vanilla UCB1, asset-count
value at leaf). See `docs/research_documents/2026-05-06-mcts-algorithm-
design.md` v2 §4 M2 for scope.

Critical preserved env quirks (per CLAUDE.md "Agent architecture"):
- ``obs`` may be a dict OR a Struct → both modules handle it.
- The ``config`` second positional arg trap: kaggle_environments passes
  its env-config Struct as the second positional arg. We MUST guard
  against treating that as our MCTSConfig. isinstance check before use.
- Always-safe heuristic fallback on any exception. The agent must never
  return invalid output to env even if MCTS code crashes.
"""

from __future__ import annotations

import time
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
    debug: dict | None = None,
) -> list[list[float | int]]:
    """Decide one turn's actions for player 0.

    Args:
        obs: Kaggle observation (dict or Struct).
        config: Either an ``MCTSConfig`` instance or the env-config Struct
            that kaggle_environments passes positionally. Only honored if
            it's actually an ``MCTSConfig``; otherwise falls back to the
            module default. (This guard mirrors the env-positional-arg
            trap documented in CLAUDE.md.)
        fallback_to_heuristic: If True, any exception or disabled MCTS
            falls through to the heuristic agent. Set False only in tests
            where you want the exception to surface.
        debug: Optional dict to receive search statistics (iterations,
            root visits, elapsed time, etc.). Useful for debugging /
            profiling.

    Returns:
        list of moves, each move shaped ``[from_planet_id, angle, ships]``.
    """
    # Late imports: avoid import-time cycles; mcts_agent stays cheap to import
    # for tests that don't actually call it.
    from orbit_wars.heuristic.strategy import agent as heuristic_agent

    # Resolve config: only trust an actual MCTSConfig instance.
    cfg = config if isinstance(config, MCTSConfig) else _DEFAULT_CFG

    # Phase M1: when disabled, delegate transparently. This is the
    # no-regression baseline.
    if not cfg.enabled:
        return heuristic_agent(obs, None)

    # Phase M2: run bare SM-MCTS.
    started = time.perf_counter()
    try:
        from .extract import extract_state_from_obs, infer_num_agents_from_obs
        from .search import search

        num_agents = infer_num_agents_from_obs(obs)
        state = extract_state_from_obs(obs, num_agents=num_agents)

        # Determine our player from obs.player. Default to 0 if missing.
        our_player = (
            int(obs.player) if hasattr(obs, "player") and obs.player is not None
            else int(obs.get("player", 0)) if hasattr(obs, "get")
            else 0
        )

        # Compute the deadline so search respects the turn budget AFTER
        # whatever extraction overhead we just incurred.
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        remaining_ms = max(cfg.turn_budget_ms - elapsed_ms, 0.0)

        # Time-pressure fallback: if too little budget left, just heuristic.
        if remaining_ms < cfg.fallback_threshold_ms:
            if debug is not None:
                debug.update({"fallback": "time_pressure", "remaining_ms": remaining_ms})
            return heuristic_agent(obs, None)

        deadline_s = time.perf_counter() + remaining_ms / 1000.0
        action_list, search_debug = search(
            state, cfg, our_player, deadline_s=deadline_s
        )
        if debug is not None:
            debug.update(search_debug)
        return action_list

    except Exception as exc:
        if not fallback_to_heuristic:
            raise
        # Always-safe fallback per CLAUDE.md "agent never returns invalid"
        if debug is not None:
            debug.update({"fallback": "exception", "error": repr(exc)})
        return heuristic_agent(obs, None)
