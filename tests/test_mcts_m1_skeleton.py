"""MCTS Phase M1 tests — skeleton wrapper validation.

M1 ships ``mcts_agent`` with ``enabled=False`` (null baseline). Tests verify:
1. The wrapper is plumbed correctly (importable, callable, returns valid moves).
2. With enabled=False, output equals the heuristic agent's output (no behavior change).
3. The env-positional-arg trap (CLAUDE.md "Agent architecture" quirk) is
   handled — passing an env Struct as the second positional doesn't crash.
4. Exception fallback works (any error inside MCTS returns a heuristic move).

These tests run live env episodes which is slow; marked ``slow`` where
appropriate.
"""
from __future__ import annotations

import pytest

from orbit_wars.heuristic.strategy import agent as heuristic_agent
from orbit_wars.mcts import MCTSConfig, mcts_agent


class TestMCTSConfigDefaults:
    """Sanity check the MCTSConfig dataclass."""

    def test_default_disabled(self) -> None:
        cfg = MCTSConfig()
        assert cfg.enabled is False, "M1 default must be disabled"

    def test_frozen(self) -> None:
        """Frozen so per-turn code can't accidentally mutate."""
        from dataclasses import FrozenInstanceError
        cfg = MCTSConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.enabled = True  # type: ignore[misc]

    def test_pw_constants_have_sane_defaults(self) -> None:
        """Per design v2 §3.5 — values that should land in the right ballpark
        even though they're not used in M1."""
        cfg = MCTSConfig()
        assert cfg.widen_c > 0
        assert 0 < cfg.widen_alpha < 1
        assert 0 < cfg.fpu_c < 1
        assert cfg.ucb_c > 1.0
        assert cfg.max_depth >= 1
        assert cfg.turn_budget_ms < 1000.0  # leave headroom under actTimeout=1s


class TestMCTSDisabledDelegatesToHeuristic:
    """When enabled=False, mcts_agent and heuristic_agent must produce the
    SAME action for the SAME observation."""

    def _run_one_turn_and_compare(self, seed: int, source_step: int) -> None:
        """Helper: run an env to source_step, capture obs, compare outputs."""
        from kaggle_environments import make
        env = make("orbit_wars", debug=True, configuration={"seed": seed})
        env.run(["random", "random"])
        obs = env.steps[source_step][0].observation
        # Both calls should produce identical move lists since MCTS is disabled.
        heuristic_out = heuristic_agent(obs, None)
        mcts_out = mcts_agent(obs, MCTSConfig(enabled=False))
        assert heuristic_out == mcts_out, (
            f"Disabled MCTS should match heuristic exactly. "
            f"heuristic={heuristic_out!r}  mcts={mcts_out!r}"
        )

    @pytest.mark.slow
    def test_matches_heuristic_at_step_5(self) -> None:
        self._run_one_turn_and_compare(seed=7, source_step=5)

    @pytest.mark.slow
    def test_matches_heuristic_mid_game(self) -> None:
        self._run_one_turn_and_compare(seed=42, source_step=50)


class TestEnvPositionalArgTrap:
    """The env's `agent(obs, config)` signature trap from CLAUDE.md.

    kaggle_environments sometimes passes its env-config Struct as the second
    positional argument. The wrapper MUST NOT mistake that for an MCTSConfig.
    """

    def _make_env_config_struct(self):
        """Synthesize the kind of object kaggle_environments passes."""
        class _EnvConfigStruct:
            episodeSteps = 500
            actTimeout = 1
            shipSpeed = 6.0
        return _EnvConfigStruct()

    @pytest.mark.slow
    def test_env_struct_does_not_crash_or_alter_behavior(self) -> None:
        """Passing an env-config Struct as `config` should be ignored —
        wrapper should fall back to module default (which is enabled=False
        → heuristic delegation). NO crash, NO behavior change."""
        from kaggle_environments import make
        env = make("orbit_wars", debug=True, configuration={"seed": 7})
        env.run(["random", "random"])
        obs = env.steps[5][0].observation
        env_struct = self._make_env_config_struct()

        out_with_struct = mcts_agent(obs, env_struct)
        out_with_none = mcts_agent(obs, None)
        assert out_with_struct == out_with_none, (
            "Env struct as second arg must be ignored; result should equal "
            "calling with config=None (which uses module default)."
        )


class TestMainPyWiring:
    """Verify the user-facing entry point in main.py is plumbed correctly."""

    def test_main_agent_is_callable(self) -> None:
        # Importing main as a module — kaggle does this when loading a submission
        import sys
        from pathlib import Path
        # main.py at src/ requires src on sys.path; let conftest or layout handle.
        src_path = str(Path(__file__).parent.parent / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        import main as main_mod
        assert callable(main_mod.agent)
        assert main_mod.MCTS_CFG.enabled is False, "M1 must ship disabled"

    @pytest.mark.slow
    def test_main_agent_returns_valid_moves_against_random(self) -> None:
        """End-to-end smoke: full game using main.agent against random.
        Validates the wrapper doesn't break Kaggle's env contract."""
        import sys
        from pathlib import Path
        src_path = str(Path(__file__).parent.parent / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        import main as main_mod
        from kaggle_environments import make
        env = make("orbit_wars", debug=True, configuration={"seed": 42})
        env.run([main_mod.agent, "random"])
        # Game must terminate (not hang or crash) and produce a final reward.
        final = env.steps[-1]
        assert final[0].reward is not None
        assert final[0].status == "DONE"


class TestMCTSEnabledFallback:
    """When enabled=True but no implementation (M1), should still return a
    valid action — falling back to heuristic. No crash."""

    @pytest.mark.slow
    def test_enabled_true_falls_back_to_heuristic(self) -> None:
        from kaggle_environments import make
        env = make("orbit_wars", debug=True, configuration={"seed": 7})
        env.run(["random", "random"])
        obs = env.steps[5][0].observation
        # Even with enabled=True, M1 has no implementation so should
        # still return a valid heuristic-shaped action list.
        out = mcts_agent(obs, MCTSConfig(enabled=True))
        # Output is a list of moves (possibly empty if no launches).
        assert isinstance(out, list)
        for move in out:
            assert isinstance(move, list)
            assert len(move) == 3  # [from_id, angle, ships]

    def test_enabled_true_no_fallback_raises(self) -> None:
        """When fallback_to_heuristic=False, M1 should raise NotImplementedError
        to make it loud during development."""
        # Use a minimal mock obs since we expect to never reach the agent code.
        # Just need a dict-shape obs.
        class _MockObs:
            planets = []
            fleets = []
            comets = []
            comet_planet_ids = []
            initial_planets = []
            angular_velocity = 0.03
            next_fleet_id = 0
            step = 5
            player = 0
            remainingOverageTime = 60.0
        with pytest.raises(NotImplementedError):
            mcts_agent(_MockObs(), MCTSConfig(enabled=True),
                       fallback_to_heuristic=False)
