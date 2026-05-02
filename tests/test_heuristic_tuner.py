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
