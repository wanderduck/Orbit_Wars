"""Tests for the CMA-ES heuristic tuning framework.

These tests run locally (no Modal calls). They validate:
1. ParamSpace covers every numeric HeuristicConfig field.
2. encode/decode round-trip preserves all field values.
3. evaluate_fitness_local runs end-to-end on a tiny budget.

Modal end-to-end testing is a manual `--smoke` run (see plan Task 12) — not in
pytest because it costs real money against the user's Modal credit.
"""

from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from orbit_wars.heuristic.config import HeuristicConfig
from tools.heuristic_tuner_param_space import (
    PARAM_SPACE,
    decode,
    encode,
    validate_param_space,
)


class TestParamSpaceCoverage:
    def test_param_space_covers_every_numeric_field(self) -> None:
        """Adding a new HeuristicConfig field must fail the test until its bound is added.

        Per spec deliverable #2: derive field list from `dataclasses.fields`,
        not by hand-enumeration.
        """
        validate_param_space()  # raises if any numeric field missing from PARAM_SPACE

    def test_param_space_excludes_booleans(self) -> None:
        """Bools (`reinforce_enabled`, `use_hungarian_offense`) are pinned, not tuned."""
        bool_fields = [f.name for f in fields(HeuristicConfig)
                       if f.type in (bool, "bool")]
        assert bool_fields, "expected at least one bool field in HeuristicConfig"
        for name in bool_fields:
            assert name not in PARAM_SPACE, f"{name} is bool — should be pinned, not in PARAM_SPACE"

    def test_param_space_bound_tuples_are_valid(self) -> None:
        """Each entry must be (lower, upper, is_int) with lower < upper."""
        for name, bounds in PARAM_SPACE.items():
            assert len(bounds) == 3, f"{name}: bounds must be (lower, upper, is_int)"
            lower, upper, is_int = bounds
            assert lower < upper, f"{name}: lower ({lower}) must be < upper ({upper})"
            assert isinstance(is_int, bool), f"{name}: is_int must be bool"


class TestEncodeDecodeRoundTrip:
    def test_default_config_round_trips_exactly(self) -> None:
        """encode(decode(encode(default))) == encode(default), per dim."""
        cfg = HeuristicConfig.default()
        x = encode(cfg)
        cfg_round = decode(x)
        x_round = encode(cfg_round)
        np.testing.assert_array_almost_equal(x, x_round, decimal=6)

    def test_decode_snaps_integer_fields_to_int(self) -> None:
        """Integer fields decoded from non-integer floats must round to ints."""
        from tools.heuristic_tuner_param_space import NUMERIC_FIELDS
        x = encode(HeuristicConfig.default())
        # Bump every field by 0.4 to force rounding for ints
        x_perturbed = x + 0.4
        cfg = decode(x_perturbed)
        for i, name in enumerate(NUMERIC_FIELDS):
            _, _, is_int = PARAM_SPACE[name]
            value = getattr(cfg, name)
            if is_int:
                assert isinstance(value, int), f"{name}: expected int, got {type(value).__name__}"
            else:
                assert isinstance(value, float), f"{name}: expected float, got {type(value).__name__}"

    def test_decode_rejects_wrong_shape(self) -> None:
        with pytest.raises(ValueError, match="expected shape"):
            decode(np.zeros(5))


class TestRunOneGame:
    def test_run_one_game_returns_finite_margin(self) -> None:
        """Run one game (default cfg vs aggressive_swarm, seed=0). Margin should be finite."""
        from tools.modal_tuner import run_one_game

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        margin = run_one_game(cfg_dict, opponent_name="aggressive_swarm", seed=0)
        # In Orbit Wars, reward margin is typically -1, 0, or +1 (sometimes float)
        assert isinstance(margin, float)
        assert -10.0 <= margin <= 10.0, f"margin {margin} outside sanity range"

    def test_run_one_game_unknown_opponent_raises(self) -> None:
        from tools.modal_tuner import run_one_game

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        with pytest.raises(KeyError):
            run_one_game(cfg_dict, opponent_name="not_a_real_opponent", seed=0)


class TestEvaluateFitnessLocal:
    def test_local_smoke_returns_well_formed_dict(self) -> None:
        """Run a tiny budget end-to-end. Verify output dict has expected keys + types."""
        from tools.modal_tuner import evaluate_fitness_local

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        result = evaluate_fitness_local(
            cfg_dict=cfg_dict,
            candidate_id=0,
            generation=0,
            sanity_n_per_opponent=2,
            fitness_n_per_opponent=2,
            sanity_threshold=0.91,
        )
        # Required keys per spec Architecture/Modal-function section
        for key in ("candidate_id", "generation", "sanity_pass", "fitness",
                    "per_opp", "sanity_winrates", "wall_clock_seconds"):
            assert key in result, f"missing key {key!r} in result"
        assert result["candidate_id"] == 0
        assert result["generation"] == 0
        assert isinstance(result["sanity_pass"], bool)
        assert isinstance(result["fitness"], float)
        assert "v15g_stock" in result["per_opp"]
        assert "peer_mdmahfuzsumon" in result["per_opp"]
        # Sanity may early-exit on first failing opponent; only require at least one entry
        assert len(result["sanity_winrates"]) >= 1

    def test_local_disqualifies_obviously_bad_config(self) -> None:
        """A clearly broken config (min_launch=999, can never afford to launch) should
        fail sanity and return fitness == DISQUALIFIED_FITNESS."""
        from tools.modal_tuner import DISQUALIFIED_FITNESS, evaluate_fitness_local

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        cfg_dict["min_launch"] = 999  # can't ever launch — will lose every game

        result = evaluate_fitness_local(
            cfg_dict=cfg_dict,
            candidate_id=99,
            generation=0,
            sanity_n_per_opponent=2,
            fitness_n_per_opponent=2,
            sanity_threshold=0.91,
        )
        assert result["sanity_pass"] is False
        assert result["fitness"] == DISQUALIFIED_FITNESS


class TestProfileAndCostGuard:
    def test_smoke_profile_under_cost_threshold(self) -> None:
        from tools.modal_tuner import _choose_profile
        pop, gens, games, cost = _choose_profile("smoke", None, None, None)
        assert pop == 4 and gens == 1 and games == 4
        assert cost < 1.0

    def test_default_profile_at_expected_cost(self) -> None:
        from tools.modal_tuner import _choose_profile
        pop, gens, games, cost = _choose_profile("default", None, None, None)
        assert pop == 50 and gens == 15 and games == 69
        assert 40.0 <= cost <= 70.0  # ~$54 plus tolerance

    def test_overrides_recompute_cost(self) -> None:
        from tools.modal_tuner import _choose_profile
        # Override popsize down → cost should drop proportionally
        _, _, _, default_cost = _choose_profile("default", None, None, None)
        _, _, _, half_cost = _choose_profile(
            "default",
            popsize_override=25,
            generations_override=None,
            fitness_games_override=None,
        )
        # Note: cost recompute formula uses 50% sanity-pass model so it may not be exactly half;
        # but it should be meaningfully smaller.
        assert half_cost < default_cost * 0.7

    def test_unknown_profile_raises(self) -> None:
        from tools.modal_tuner import _choose_profile
        with pytest.raises(ValueError, match="Unknown profile"):
            _choose_profile("not_a_profile", None, None, None)
