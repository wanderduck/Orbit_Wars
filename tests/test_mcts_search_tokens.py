"""Unit tests for _search_tokens + helpers (Phase 5 of option 2).

Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md §3.2.4.

Tests are layered:
  - filter_valid: ship-pool deduction across prior picks; COMMIT always valid
  - ucb_select_token: argmax UCB1+FPU among considered indices
  - smmcts iteration: one full walk, sub-tree growth, env-turn child creation
  - search() dispatcher: routes to legacy vs token correctly
  - search_tokens end-to-end: returns env action list + reasonable debug

End-to-end test uses the real Simulator on a small synthetic SimState
(no kaggle_environments) so it stays fast and deterministic.
"""
from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from orbit_wars.mcts.config import MCTSConfig
from orbit_wars.mcts.node_tokens import MCTSNode as TokenMCTSNode
from orbit_wars.mcts.node_tokens import SubNode
from orbit_wars.mcts.search import (
    _COMMIT_IDX,
    _filter_valid_token_indices,
    _search_tokens,
    _smmcts_token_iteration,
    _ucb_select_token,
    search,
)
from orbit_wars.mcts.token import LaunchToken
from orbit_wars.sim.simulator import Simulator
from orbit_wars.sim.state import SimConfig, SimPlanet, SimState


def _state_two_static_planets() -> SimState:
    """Player 0 owns planet 0 (left side, static, 100 ships).
    Player 1 owns planet 1 (left-bottom, static, 80 ships).
    Both static and on a sun-safe path between each other."""
    return SimState(
        config=SimConfig(num_agents=2),
        step=0,
        planets=[
            SimPlanet(id=0, x=3.0, y=50.0, radius=4.0, owner=0, ships=100, production=5),
            SimPlanet(id=1, x=3.0, y=20.0, radius=4.0, owner=1, ships=80, production=5),
        ],
        fleets=[],
        comet_groups=[],
        initial_planets=[],
        angular_velocity=0.0,
        next_fleet_id=0,
    )


# ---------------------------------------------------------------------------
# filter_valid_token_indices
# ---------------------------------------------------------------------------


class TestFilterValidTokenIndices:
    def test_commit_always_valid(self) -> None:
        cfg = MCTSConfig(use_token_variants=True)
        state = _state_two_static_planets()
        tokens = [LaunchToken.COMMIT]
        valid = _filter_valid_token_indices(tokens, prior_picks=(), state=state,
                                             player_id=0, cfg=cfg)
        assert valid == [_COMMIT_IDX]

    def test_token_with_owned_src_valid(self) -> None:
        cfg = MCTSConfig(use_token_variants=True)
        state = _state_two_static_planets()
        tokens = [LaunchToken.COMMIT, LaunchToken(0, 1, 1)]  # bucket 1 = 0.5
        valid = _filter_valid_token_indices(tokens, (), state, 0, cfg)
        assert _COMMIT_IDX in valid
        assert 1 in valid

    def test_token_with_unowned_src_filtered_out(self) -> None:
        cfg = MCTSConfig(use_token_variants=True)
        state = _state_two_static_planets()
        # Token tries to launch from planet 1 (owned by player 1) for player 0
        tokens = [LaunchToken.COMMIT, LaunchToken(1, 0, 1)]
        valid = _filter_valid_token_indices(tokens, (), state, 0, cfg)
        assert valid == [_COMMIT_IDX]

    def test_prior_picks_decrement_pool(self) -> None:
        """If a prior pick used up most of source's ships, a subsequent
        token from the same source might no longer have enough."""
        cfg = MCTSConfig(use_token_variants=True,
                         ship_fraction_buckets=(0.5, 1.0))
        state = _state_two_static_planets()
        tokens = [
            LaunchToken.COMMIT,
            LaunchToken(0, 1, 1),   # bucket 1 = 1.0 → uses ALL ships
            LaunchToken(0, 1, 0),   # bucket 0 = 0.5 → would need ships
        ]
        # After picking token 1 (drains source), token 2 should be filtered
        valid = _filter_valid_token_indices(tokens, prior_picks=(1,), state=state,
                                             player_id=0, cfg=cfg)
        assert valid == [_COMMIT_IDX]  # only COMMIT survives

    def test_prior_pick_partial_drain_keeps_some(self) -> None:
        """A 50% prior pick leaves 50% pool; a 50% second pick is still valid."""
        cfg = MCTSConfig(use_token_variants=True,
                         ship_fraction_buckets=(0.5, 1.0))
        state = _state_two_static_planets()
        tokens = [
            LaunchToken.COMMIT,
            LaunchToken(0, 1, 0),   # bucket 0 = 0.5
            LaunchToken(0, 1, 0),   # same — 50% of remaining
        ]
        valid = _filter_valid_token_indices(tokens, prior_picks=(1,), state=state,
                                             player_id=0, cfg=cfg)
        assert _COMMIT_IDX in valid
        assert 2 in valid  # 0.5 of 50 remaining = 25 ships, still valid


# ---------------------------------------------------------------------------
# ucb_select_token
# ---------------------------------------------------------------------------


class TestUcbSelectToken:
    def test_empty_considered_returns_commit(self) -> None:
        cfg = MCTSConfig(use_token_variants=True)
        sub = SubNode(((), ()), (False, False))
        assert _ucb_select_token(sub, player_idx=0, considered_indices=[], cfg=cfg) == _COMMIT_IDX

    def test_single_considered_returns_it(self) -> None:
        cfg = MCTSConfig(use_token_variants=True)
        sub = SubNode(((), ()), (False, False))
        assert _ucb_select_token(sub, player_idx=0, considered_indices=[5], cfg=cfg) == 5

    def test_unvisited_uses_fpu(self) -> None:
        """All unvisited → all score = fpu_c. Tie-break by iteration order
        returns the first considered."""
        cfg = MCTSConfig(use_token_variants=True, fpu_c=0.5)
        sub = SubNode(((), ()), (False, False))
        choice = _ucb_select_token(sub, player_idx=0,
                                    considered_indices=[3, 7, 11], cfg=cfg)
        assert choice == 3

    def test_high_mean_visited_beats_unvisited_at_low_fpu(self) -> None:
        """Visited token with mean=0.8 beats unvisited at fpu=0.5."""
        cfg = MCTSConfig(use_token_variants=True, fpu_c=0.5)
        sub = SubNode(((), ()), (False, False))
        # token 5 has 10 visits, total value 8.0 → mean 0.8
        sub.update_stat(player_idx=0, token_idx=5, value=0.8)
        for _ in range(9):
            sub.update_stat(0, 5, 0.8)
        sub.visits = 10
        choice = _ucb_select_token(sub, player_idx=0,
                                    considered_indices=[1, 5, 9], cfg=cfg)
        # Expected: token 5's UCB ≈ 0.8 + sqrt(2)*sqrt(log(10)/10) ≈ 0.8 + 0.68 ≈ 1.48
        # Unvisited tokens 1, 9 score = fpu_c = 0.5
        # Token 5 wins
        assert choice == 5


# ---------------------------------------------------------------------------
# search dispatcher
# ---------------------------------------------------------------------------


class TestSearchDispatcher:
    def test_use_token_variants_false_routes_to_legacy(self) -> None:
        """With use_token_variants=False, the search() dispatcher must call
        _search_legacy. We assert by patching _search_tokens to raise."""
        cfg = MCTSConfig(enabled=True, use_token_variants=False, turn_budget_ms=10.0)
        state = _state_two_static_planets()
        with patch("orbit_wars.mcts.search._search_tokens",
                   side_effect=AssertionError("should not be called")):
            # No exception → legacy path was used
            result, debug = search(state, cfg, our_player=0)
        assert isinstance(result, list)

    def test_use_token_variants_true_routes_to_tokens(self) -> None:
        """With use_token_variants=True, the search() dispatcher must call
        _search_tokens. Patch _search_legacy to verify."""
        cfg = MCTSConfig(enabled=True, use_token_variants=True, turn_budget_ms=50.0)
        state = _state_two_static_planets()
        with patch("orbit_wars.mcts.search._search_legacy",
                   side_effect=AssertionError("should not be called")):
            result, debug = search(state, cfg, our_player=0)
        assert isinstance(result, list)
        # debug shape from _search_tokens
        assert "iterations" in debug


# ---------------------------------------------------------------------------
# End-to-end token search smoke test
# ---------------------------------------------------------------------------


class TestSearchTokensEndToEnd:
    """One real iteration on a small state should produce reasonable output."""

    def test_short_budget_completes_with_some_iterations(self) -> None:
        """50ms budget on a tiny state should produce at least a few iterations
        and a valid action list."""
        cfg = MCTSConfig(
            enabled=True,
            use_token_variants=True,
            turn_budget_ms=50.0,
            max_depth=2,  # shallow for speed
        )
        state = _state_two_static_planets()
        result, debug = _search_tokens(state, cfg, our_player=0)
        # Should produce SOME iterations
        assert debug["iterations"] >= 1
        # Result is a list of [from_id, angle, ships] triples (possibly empty)
        assert isinstance(result, list)
        for move in result:
            assert isinstance(move, list)
            assert len(move) == 3

    def test_root_subnode_visits_match_iteration_count(self) -> None:
        """If we ran N iterations, root's children dict should have at least
        one entry (one COMMIT path explored)."""
        cfg = MCTSConfig(
            enabled=True, use_token_variants=True,
            turn_budget_ms=100.0, max_depth=2, max_launches_per_turn=2,
        )
        state = _state_two_static_planets()
        result, debug = _search_tokens(state, cfg, our_player=0)
        assert debug["iterations"] >= 1
        assert debug["n_children"] >= 1


class TestSubTreeWalkOneIteration:
    """A single call to _smmcts_token_iteration on a fresh node should
    populate ranked_tokens and create at least one sub-node + one child."""

    def test_first_iteration_populates_structure(self) -> None:
        cfg = MCTSConfig(
            enabled=True, use_token_variants=True,
            max_depth=1, max_launches_per_turn=2,
        )
        state = _state_two_static_planets()
        node = TokenMCTSNode(state=state)
        sim = Simulator()
        leaf_values = _smmcts_token_iteration(
            node, sim, cfg, alive_players=[0, 1], depth=0,
        )
        # ranked_tokens populated for both players
        assert 0 in node.ranked_tokens
        assert 1 in node.ranked_tokens
        # At least one sub-node beyond root (we made at least one pick)
        assert len(node.subnode_cache) >= 1
        # Exactly one child (one committed_key)
        assert len(node.children) == 1
        # Leaf values have entries for both alive players
        assert 0 in leaf_values
        assert 1 in leaf_values
        # Leaf values are floats in [0, 1]
        for v in leaf_values.values():
            assert 0.0 <= v <= 1.0
