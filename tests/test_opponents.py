"""Smoke tests for local sparring partners.

Each opponent must (a) import without raising, (b) expose a callable
``agent``, (c) not crash inside a single episode against ``random``.

Marked ``@pytest.mark.slow`` because spinning up the env and running a full
episode takes a few seconds; run with ``uv run pytest -m slow`` to include.
"""

from __future__ import annotations

import importlib

import pytest
from kaggle_environments import make

_OPPONENTS = [
    "orbit_wars.opponents.competent_sniper",
    "orbit_wars.opponents.aggressive_swarm",
    "orbit_wars.opponents.defensive_turtle",
    "orbit_wars.opponents.peer_mdmahfuzsumon",
]


@pytest.mark.parametrize("module_path", _OPPONENTS)
def test_opponent_imports_and_exposes_callable(module_path: str) -> None:
    module = importlib.import_module(module_path)
    assert hasattr(module, "agent"), f"{module_path} must expose an `agent` function"
    assert callable(module.agent), f"{module_path}.agent must be callable"


@pytest.mark.slow
@pytest.mark.parametrize("module_path", _OPPONENTS)
def test_opponent_survives_one_episode_vs_random(module_path: str) -> None:
    module = importlib.import_module(module_path)
    env = make("orbit_wars", debug=False, configuration={"seed": 0})
    env.run([module.agent, "random"])
    final = env.steps[-1]
    assert final[0].status in {"DONE", "INVALID", "ACTIVE"}, (
        f"{module_path} ended with unexpected status {final[0].status}"
    )
