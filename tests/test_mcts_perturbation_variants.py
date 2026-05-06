"""Unit tests for the heuristic-perturbation variant generator (option 1).

Replaces the prior lightweight nearest-target drop-one variants in
src/orbit_wars/mcts/ranking.py:ranked_actions_with_heuristic. Per
mcts_m2_0wins_20games.md: M3 picked variant 0 (heuristic) 99-100% of
turns under the old variant set because the lightweight perturbations
were strictly worse than the heuristic. The new variants are
heuristic-DERIVED (drop-one of the heuristic's own launches), giving
MCTS at least a plausibly-better candidate set.

These tests mock decide_with_decisions to control the heuristic's
launch list and assert the variant generator produces the right shape.
SimState is also stubbed — the variant generator's only contract with
state is "pass it to _simstate_to_env_dict + decide_with_decisions"
which we mock.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from orbit_wars.mcts.ranking import ranked_actions_with_heuristic


# A "fake" SimState — passed through to the mocked decide_with_decisions.
# The generator calls _simstate_to_env_dict(state) so we also have to mock
# that to accept any input.
class FakeSimState:
    """Stand-in for SimState — only needs to be passable to mocked deps."""


def _patch_helpers(launches_to_return):
    """Patch _simstate_to_env_dict and decide_with_decisions consistently
    so the variant generator runs to completion with a controlled launch
    list. Returns the patcher context managers.
    """
    return [
        patch("orbit_wars.sim.validator._simstate_to_env_dict",
              return_value={"step": 0, "planets": [], "fleets": [], "comets": [],
                            "comet_planet_ids": [], "initial_planets": [],
                            "angular_velocity": 0.0, "next_fleet_id": 0}),
        patch("orbit_wars.heuristic.strategy.decide_with_decisions",
              return_value=(launches_to_return, [])),
    ]


class TestHeuristicHoldCase:
    """When heuristic returns no launches, only HOLD is meaningful."""

    def test_empty_launches_returns_only_hold(self) -> None:
        with _patch_helpers([])[0], _patch_helpers([])[1]:
            variants = ranked_actions_with_heuristic(FakeSimState(), 0, k=8)
        assert variants == [[]]


class TestSingleLaunchCase:
    """One heuristic launch → [v0=launch, v1=HOLD]. Drop-one would
    duplicate HOLD, so it's skipped."""

    def test_one_launch_no_drop_one_duplicate(self) -> None:
        L1 = [3, 0.5, 100]
        with _patch_helpers([L1])[0], _patch_helpers([L1])[1]:
            variants = ranked_actions_with_heuristic(FakeSimState(), 0, k=8)
        assert variants == [[L1], []]


class TestThreeLaunchCase:
    """Three launches with k=8 → v0=all, v1=HOLD, v2=drop-L3, v3=drop-L2,
    v4=drop-L1. Exactly 5 variants total."""

    def test_three_launches_full_drop_one_coverage(self) -> None:
        L1, L2, L3 = [1, 0.0, 50], [2, 1.0, 60], [3, 2.0, 70]
        with _patch_helpers([L1, L2, L3])[0], _patch_helpers([L1, L2, L3])[1]:
            variants = ranked_actions_with_heuristic(FakeSimState(), 0, k=8)
        # v0 = all three launches
        assert variants[0] == [L1, L2, L3]
        # v1 = HOLD
        assert variants[1] == []
        # v2 = drop the LAST launch (heuristic's lowest-priority pick)
        assert variants[2] == [L1, L2]
        # v3 = drop the second-to-last
        assert variants[3] == [L1, L3]
        # v4 = drop the FIRST launch (highest-priority — least likely regret)
        assert variants[4] == [L2, L3]
        assert len(variants) == 5

    def test_drop_priority_is_lowest_first(self) -> None:
        """Drop launches[-1] before launches[-2] before launches[0]. This is
        deliberate: the heuristic's lowest-priority launch is the most
        likely net-negative call (borderline scoring); test it first."""
        L1, L2, L3 = [1, 0.0, 50], [2, 1.0, 60], [3, 2.0, 70]
        with _patch_helpers([L1, L2, L3])[0], _patch_helpers([L1, L2, L3])[1]:
            variants = ranked_actions_with_heuristic(FakeSimState(), 0, k=8)
        # The first drop-one variant (v2) must omit L3 (the last/lowest).
        # The last drop-one variant (v4) must omit L1 (the first/highest).
        assert L3 not in variants[2]
        assert L1 in variants[2]
        assert L1 not in variants[-1]
        assert L3 in variants[-1]


class TestKBudgetTruncation:
    """If k is smaller than v0+v1+drop-one count, drop-one slots are
    truncated. With 6 launches and k=4, we get [v0, v1, drop-L6, drop-L5]."""

    def test_k_4_with_6_launches(self) -> None:
        launches = [[i, 0.0, 100] for i in range(6)]  # L0..L5
        with _patch_helpers(launches)[0], _patch_helpers(launches)[1]:
            variants = ranked_actions_with_heuristic(FakeSimState(), 0, k=4)
        assert len(variants) == 4
        assert variants[0] == launches
        assert variants[1] == []
        # v2 = drop launches[-1] (i.e., launches[5])
        assert variants[2] == launches[:5]
        # v3 = drop launches[-2] (i.e., launches[4])
        assert variants[3] == launches[:4] + [launches[5]]


class TestKLargerThanLaunchCount:
    """If k > v0 + v1 + len(launches), all drop-one variants fit and
    we don't pad with anything else."""

    def test_k_8_with_2_launches(self) -> None:
        L1, L2 = [1, 0.0, 50], [2, 1.0, 60]
        with _patch_helpers([L1, L2])[0], _patch_helpers([L1, L2])[1]:
            variants = ranked_actions_with_heuristic(FakeSimState(), 0, k=8)
        # v0=all, v1=HOLD, v2=drop-L2, v3=drop-L1 = 4 variants total
        assert len(variants) == 4
        assert variants[0] == [L1, L2]
        assert variants[1] == []
        assert variants[2] == [L1]  # dropped L2
        assert variants[3] == [L2]  # dropped L1


class TestNoStrictlyWorseLightweightVariants:
    """Regression test: the new variants must NOT include the prior
    lightweight nearest-target drops. Verify variant content is purely
    heuristic-derived."""

    def test_variants_are_heuristic_derived_only(self) -> None:
        """Every drop-one variant is a SUBSEQUENCE of the heuristic launches.
        No "lightweight-ranker" launches should appear."""
        # If the heuristic returned launches with these specific (planet_id,
        # angle, ships) tuples, every non-HOLD variant should only contain
        # subsets of THIS list — no extras.
        heuristic_marker = [99, 99.0, 999]  # impossible-looking ID
        L1 = heuristic_marker
        L2 = [88, 88.0, 888]
        with _patch_helpers([L1, L2])[0], _patch_helpers([L1, L2])[1]:
            variants = ranked_actions_with_heuristic(FakeSimState(), 0, k=8)
        for v in variants:
            for launch in v:
                # Every launch in any variant must be one of the heuristic's
                assert launch in [L1, L2], (
                    f"Variant contained non-heuristic launch {launch} — "
                    f"the perturbation generator should NEVER inject "
                    f"launches the heuristic did not produce."
                )
