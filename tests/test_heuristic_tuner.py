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
        """Run a tiny budget end-to-end. Verify output dict has expected keys + types.

        Plan A retool: per_opp now contains a single key "4p_graduated" (was the
        2P anchor + per-archive matchups before).
        """
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
        # 4P retool: per_opp has the single graduated-score entry
        assert set(result["per_opp"].keys()) == {"4p_graduated"}
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
        """Plan A 4P retool: default profile is 50 popsize × 15 gens × 33 4P games."""
        from tools.modal_tuner import _choose_profile
        pop, gens, games, cost = _choose_profile("default", None, None, None)
        assert pop == 50 and gens == 15 and games == 33
        # ~$130 baseline cost projection; cost meter overestimates 4-5x per
        # CLAUDE.md memory, so this is a wide tolerance band.
        assert 50.0 <= cost <= 250.0

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


class TestRollingArchive:
    def test_avg_archive_size_warmup(self) -> None:
        """During warmup (first interval gens), archive is empty."""
        from tools.modal_tuner import _avg_archive_size_during_run
        # 3 gens, interval=3, max=3 → all warmup → avg = 0
        assert _avg_archive_size_during_run(3, 3, 3) == 0.0

    def test_avg_archive_size_filled_run(self) -> None:
        """For a long run, archive saturates at max_size for most gens."""
        from tools.modal_tuner import _avg_archive_size_during_run
        # 30 gens, interval=3, max=3:
        # gens 0-2: 0, 3-5: 1, 6-8: 2, 9-29: 3 (cap)
        # total = 0+0+0+1+1+1+2+2+2+(21*3) = 9+63 = 72; avg = 72/30 = 2.4
        avg = _avg_archive_size_during_run(30, 3, 3)
        assert abs(avg - 2.4) < 0.01

    def test_avg_archive_size_default_profile(self) -> None:
        """For default profile (15 gens, interval=3, max=3): avg ~1.8."""
        from tools.modal_tuner import _avg_archive_size_during_run
        # gens 0-2: 0, 3-5: 1, 6-8: 2, 9-14: 3 → total = 0+0+0+1+1+1+2+2+2+3+3+3+3+3+3 = 27
        # avg = 27/15 = 1.8
        avg = _avg_archive_size_during_run(15, 3, 3)
        assert abs(avg - 1.8) < 0.01

    def test_evaluate_fitness_local_with_archive(self) -> None:
        """evaluate_fitness_local with 1-2 archive entries: opponents mix archive + starter.

        Plan A retool: per_opp shape changed to {"4p_graduated": <score>} —
        no longer per-opponent (4P games combine 3 opponents per game).
        Verifies the function accepts archive_opponents without error and
        produces a graduated score.
        """
        from tools.modal_tuner import evaluate_fitness_local

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        # Use a 2nd config (slight tweak) as archive entry
        archive_cfg = dict(cfg_dict)
        archive_cfg["min_launch"] = 30  # different from default's 20

        archive_opponents = [
            {"name": "archive_test_0", "cfg_dict": archive_cfg},
        ]
        result = evaluate_fitness_local(
            cfg_dict=cfg_dict,
            candidate_id=0,
            generation=10,
            sanity_n_per_opponent=2,
            fitness_n_per_opponent=2,
            sanity_threshold=0.91,
            archive_opponents=archive_opponents,
        )
        # per_opp shape changed for 4P retool — single graduated key
        assert set(result["per_opp"].keys()) == {"4p_graduated"}
        assert isinstance(result["fitness"], float)
        assert -1.0 <= result["fitness"] <= 1.0

    def test_evaluate_fitness_local_4p_no_archive_uses_starter_opponents(self) -> None:
        """When archive_opponents is None, fitness phase plays 4P vs 3 starters
        and returns mean graduated score (range [-1, +1]).

        Replaces the old 2P backward-compat test (Plan A retool, 2026-05-05).
        """
        from tools.modal_tuner import evaluate_fitness_local

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        result = evaluate_fitness_local(
            cfg_dict=cfg_dict,
            candidate_id=0,
            generation=0,
            sanity_n_per_opponent=2,
            fitness_n_per_opponent=2,    # only 2 4P games for speed in this test
            sanity_threshold=0.91,
            archive_opponents=None,
        )
        # Single key in per_opp — graduated 4P score.
        assert set(result["per_opp"].keys()) == {"4p_graduated"}
        # fitness equals the per_opp value
        assert result["fitness"] == pytest.approx(result["per_opp"]["4p_graduated"])
        # Graduated scores are in [-1, +1] → mean is also in that range.
        assert -1.0 <= result["fitness"] <= 1.0
        # Default config vs 3 starters should typically score positively
        # (heuristic agent beats random launch ratio of starter), but we
        # don't assert that strictly — small sample size + RNG variance.


class TestGraduatedScores:
    """Test the 4P graduated placement scoring helper (Plan A retool)."""

    def test_no_ties_returns_canonical_ranks(self) -> None:
        from tools.modal_tuner import graduated_scores
        scores = graduated_scores([100.0, 50.0, 30.0, 0.0])
        assert scores == [1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0]

    def test_scores_returned_in_input_order(self) -> None:
        """Player 2 has the highest count → result[2] == +1."""
        from tools.modal_tuner import graduated_scores
        scores = graduated_scores([10.0, 30.0, 100.0, 50.0])
        assert scores[2] == 1.0          # rank 1
        assert scores[3] == 1.0 / 3.0    # rank 2
        assert scores[1] == -1.0 / 3.0   # rank 3
        assert scores[0] == -1.0         # rank 4

    def test_two_way_tie_at_top_averages_first_two_ranks(self) -> None:
        from tools.modal_tuner import graduated_scores
        scores = graduated_scores([100.0, 100.0, 30.0, 0.0])
        # Players 0,1 tied at top → avg(1, 1/3) = 2/3
        assert scores[0] == pytest.approx(2.0 / 3.0)
        assert scores[1] == pytest.approx(2.0 / 3.0)
        assert scores[2] == pytest.approx(-1.0 / 3.0)
        assert scores[3] == pytest.approx(-1.0)

    def test_three_way_tie_at_bottom(self) -> None:
        from tools.modal_tuner import graduated_scores
        scores = graduated_scores([100.0, 50.0, 50.0, 50.0])
        # Players 1,2,3 tied → avg(1/3, -1/3, -1) = -1/3
        assert scores[0] == 1.0
        assert scores[1] == pytest.approx(-1.0 / 3.0)
        assert scores[2] == pytest.approx(-1.0 / 3.0)
        assert scores[3] == pytest.approx(-1.0 / 3.0)

    def test_all_tied_each_gets_zero(self) -> None:
        from tools.modal_tuner import graduated_scores
        scores = graduated_scores([50.0, 50.0, 50.0, 50.0])
        # avg(1, 1/3, -1/3, -1) = 0
        for s in scores:
            assert s == pytest.approx(0.0)

    def test_sum_is_zero_zero_sum_invariant(self) -> None:
        """Whatever the rankings, total scores sum to zero (zero-sum tournament)."""
        from tools.modal_tuner import graduated_scores
        for asset_counts in (
            [100.0, 50.0, 30.0, 0.0],
            [100.0, 100.0, 30.0, 0.0],
            [50.0, 50.0, 50.0, 50.0],
            [100.0, 50.0, 50.0, 50.0],
            [0.0, 0.0, 0.0, 1.0],
        ):
            scores = graduated_scores(asset_counts)
            assert sum(scores) == pytest.approx(0.0)

    def test_rejects_non_4p_input(self) -> None:
        from tools.modal_tuner import graduated_scores
        with pytest.raises(ValueError):
            graduated_scores([1.0, 2.0])
        with pytest.raises(ValueError):
            graduated_scores([1.0, 2.0, 3.0])
        with pytest.raises(ValueError):
            graduated_scores([1.0, 2.0, 3.0, 4.0, 5.0])


class TestComputePlayerAssets:
    """Test the per-player asset count helper (Plan A retool)."""

    def _make_obs(self, planets, fleets):
        """Helper: minimal env-like obs object with .planets and .fleets."""
        class _Obs:
            pass
        obs = _Obs()
        obs.planets = planets
        obs.fleets = fleets
        return obs

    def test_planets_only_summed_per_owner(self) -> None:
        from tools.modal_tuner import compute_player_assets
        # planets shape: [id, owner, x, y, radius, ships, prod]
        obs = self._make_obs(
            planets=[
                [0, 0, 0, 0, 2, 50, 1],   # player 0: 50 ships
                [1, 1, 0, 0, 2, 30, 1],   # player 1: 30 ships
                [2, -1, 0, 0, 2, 100, 1], # neutral: not counted
            ],
            fleets=[],
        )
        assets = compute_player_assets(obs)
        assert assets[0] == 50.0
        assert assets[1] == 30.0

    def test_fleets_added_to_owner_assets(self) -> None:
        from tools.modal_tuner import compute_player_assets
        obs = self._make_obs(
            planets=[[0, 0, 0, 0, 2, 50, 1]],
            # fleets shape: [id, owner, x, y, angle, from_id, ships]
            fleets=[
                [0, 0, 5, 5, 0, 0, 10],   # player 0 fleet: +10 ships
                [1, 1, 5, 5, 0, 0, 25],   # player 1 fleet: 25 ships
            ],
        )
        assets = compute_player_assets(obs)
        assert assets[0] == 60.0  # 50 planet + 10 fleet
        assert assets[1] == 25.0  # 0 planet + 25 fleet

    def test_neutral_planets_not_counted_for_anyone(self) -> None:
        from tools.modal_tuner import compute_player_assets
        obs = self._make_obs(
            planets=[
                [0, 0, 0, 0, 2, 50, 1],
                [1, -1, 0, 0, 2, 999, 1],  # neutral with huge ship count
            ],
            fleets=[],
        )
        assets = compute_player_assets(obs)
        assert assets[0] == 50.0
        assert sum(assets) == 50.0  # neutral 999 not in any player's total


class TestSelect4pOpponents:
    """Test the 4P opponent sampling helper (Plan A retool)."""

    def test_full_archive_samples_three_without_replacement(self) -> None:
        import random as r
        from tools.modal_tuner import _select_4p_opponents
        archive = [
            {"name": "best-g3", "cfg_dict": {"a": 1}},
            {"name": "best-g6", "cfg_dict": {"a": 2}},
            {"name": "best-g9", "cfg_dict": {"a": 3}},
            {"name": "best-g12", "cfg_dict": {"a": 4}},
            {"name": "best-g15", "cfg_dict": {"a": 5}},
        ]
        chosen = _select_4p_opponents(archive, num_needed=3, rng=r.Random(42))
        assert len(chosen) == 3
        # All from archive (no fallback needed)
        names = [c["name"] for c in chosen if isinstance(c, dict)]
        assert len(names) == 3
        # No duplicates
        assert len(set(names)) == 3

    def test_empty_archive_falls_back_to_starter_for_all(self) -> None:
        from tools.modal_tuner import _select_4p_opponents
        chosen = _select_4p_opponents([], num_needed=3)
        assert chosen == ["starter", "starter", "starter"]

    def test_partial_archive_uses_all_then_pads_with_starter(self) -> None:
        from tools.modal_tuner import _select_4p_opponents
        archive = [{"name": "best-g3", "cfg_dict": {"a": 1}}]
        chosen = _select_4p_opponents(archive, num_needed=3)
        assert len(chosen) == 3
        # First the 1 archive entry, then 2 starters
        assert chosen[0] == archive[0]
        assert chosen[1] == "starter"
        assert chosen[2] == "starter"

    def test_seeded_rng_gives_reproducible_sample(self) -> None:
        import random as r
        from tools.modal_tuner import _select_4p_opponents
        archive = [
            {"name": f"best-g{i}", "cfg_dict": {"i": i}} for i in range(10)
        ]
        a = _select_4p_opponents(archive, num_needed=3, rng=r.Random(7))
        b = _select_4p_opponents(archive, num_needed=3, rng=r.Random(7))
        assert [c["name"] for c in a] == [c["name"] for c in b]
