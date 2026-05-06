"""Convert a live Kaggle observation to SimState for MCTS planning.

Mirrors `validator.extract_state_and_actions` but for the LIVE obs the
agent receives at each turn (no env.steps available — agent only sees
the current obs). Reuses the validator's private `_env_dict_to_simstate`
since the data shape is identical between env.steps[i].observation and
the live obs.

Critical env quirk (CLAUDE.md "Agent architecture"): obs may be a dict
OR a Struct. Use `_obs_get` to handle both transparently.
"""
from __future__ import annotations

import copy
from typing import Any

from orbit_wars.sim.state import SimState
from orbit_wars.sim.validator import _env_dict_to_simstate


def _obs_get(obs: Any, key: str, default: Any = None) -> Any:
    """Read `key` from obs whether it's a dict or a Struct."""
    if hasattr(obs, key):
        return getattr(obs, key)
    if hasattr(obs, "get"):
        return obs.get(key, default)
    return default


def extract_state_from_obs(obs: Any, num_agents: int = 2) -> SimState:
    """Convert a live Kaggle obs to typed SimState.

    `num_agents` defaults to 2 because that's the most common case (and
    the env doesn't expose num_agents on obs directly — we infer it from
    config or pass it in). For 4P FFA, callers should pass num_agents=4.

    Returns a fresh SimState — caller can pass directly to Simulator.step().
    """
    state_dict = {
        "step": _obs_get(obs, "step"),
        "planets": copy.deepcopy(list(_obs_get(obs, "planets", []) or [])),
        "fleets": copy.deepcopy(list(_obs_get(obs, "fleets", []) or [])),
        "comets": copy.deepcopy(list(_obs_get(obs, "comets", []) or [])),
        "comet_planet_ids": list(_obs_get(obs, "comet_planet_ids", []) or []),
        "initial_planets": copy.deepcopy(
            list(_obs_get(obs, "initial_planets", []) or [])
        ),
        "angular_velocity": _obs_get(obs, "angular_velocity"),
        "next_fleet_id": _obs_get(obs, "next_fleet_id"),
    }
    return _env_dict_to_simstate(state_dict, num_agents=num_agents)


def infer_num_agents_from_obs(obs: Any) -> int:
    """Best-effort inference of num_agents (2 or 4) from observation.

    Heuristic: count distinct non-neutral planet owners + fleet owners.
    Defaults to 2 if no owned bodies (e.g., very early game state).
    """
    owners: set[int] = set()
    for p in _obs_get(obs, "planets", []) or []:
        if p[1] != -1:
            owners.add(p[1])
    for f in _obs_get(obs, "fleets", []) or []:
        owners.add(f[1])
    if not owners:
        return 2
    # If any owner > 1 we must be in 4P
    return 4 if max(owners) >= 2 else 2
