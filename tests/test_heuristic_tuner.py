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
