"""Unit tests for the token generator (Phase 2 of option 2).

Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md §5.1.

These tests mock decide_with_decisions + _simstate_to_env_dict to control the
heuristic's output deterministically. The real heuristic is exercised in
test_mcts_serialize.py (the parity test, Risk 2 gate).
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from orbit_wars.heuristic.strategy import LaunchDecision
from orbit_wars.mcts.config import MCTSConfig
from orbit_wars.mcts.token import LaunchToken
from orbit_wars.mcts.tokens import (
    extend_with_long_tail,
    generate_ranked_tokens,
)


@dataclass(slots=True)
class FakePlanet:
    """Minimal stand-in for SimPlanet — generate_ranked_tokens only reads
    planet_by_id(), .ships, .owner, .x, .y."""
    id: int
    owner: int
    ships: int
    x: float = 0.0
    y: float = 0.0


@dataclass(slots=True)
class FakeState:
    """Minimal stand-in for SimState — generate_ranked_tokens calls
    planet_by_id() and (for long-tail) iterates .planets."""
    planets: list[FakePlanet]

    def planet_by_id(self, pid: int) -> FakePlanet | None:
        for p in self.planets:
            if p.id == pid:
                return p
        return None


def _make_decision(src_id: int, target_id: int, ships: int) -> LaunchDecision:
    """Build a LaunchDecision with sane defaults for fields the generator
    doesn't care about. Only src_id, target_id, ships are read."""
    return LaunchDecision(
        src_id=src_id,
        target_id=target_id,
        angle=0.0,
        ships=ships,
        eta=10,
        src_ships_pre_launch=ships * 2,  # arbitrary
        target_ships_at_launch=0,
        target_owner=-1,
        target_x=0.0,
        target_y=0.0,
        target_radius=1.0,
        target_is_static=True,
        target_is_comet=False,
    )


def _patches(decisions_to_return: list[LaunchDecision]):
    """Patch context for both helpers the generator depends on. Returns a
    list of context managers — caller wraps in ExitStack."""
    return [
        patch(
            "orbit_wars.mcts.tokens._simstate_to_env_dict",
            return_value={
                "step": 0,
                "planets": [],
                "fleets": [],
                "comets": [],
                "comet_planet_ids": [],
                "initial_planets": [],
                "angular_velocity": 0.0,
                "next_fleet_id": 0,
            },
        ),
        patch(
            "orbit_wars.mcts.tokens.decide_with_decisions",
            return_value=([], decisions_to_return),
        ),
    ]


class TestEmptyHeuristicOutput:
    def test_no_decisions_returns_only_commit(self) -> None:
        cfg = MCTSConfig(use_token_variants=True)
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=10)])
        with ExitStack() as stack:
            for p in _patches([]):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        assert tokens == [LaunchToken.COMMIT]


class TestCommitAtIndexZero:
    def test_commit_always_first(self) -> None:
        """Per design §5.2 — COMMIT at index 0 is critical for PW behavior."""
        cfg = MCTSConfig(use_token_variants=True)
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=100)])
        decisions = [_make_decision(src_id=0, target_id=1, ships=50)]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        assert tokens[0] == LaunchToken.COMMIT
        assert tokens[0].is_commit()


class TestTokensPerDecision:
    def test_default_three_buckets_per_decision(self) -> None:
        """Default tokens_per_decision=3 → 3 token-variants per LaunchDecision."""
        cfg = MCTSConfig(use_token_variants=True, tokens_per_decision=3)
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=100)])
        decisions = [_make_decision(src_id=0, target_id=1, ships=50)]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        # 1 COMMIT + 3 buckets × 1 decision = 4 tokens
        assert len(tokens) == 4

    def test_one_bucket_per_decision(self) -> None:
        """tokens_per_decision=1 → only the heuristic's exact bucket per decision."""
        cfg = MCTSConfig(use_token_variants=True, tokens_per_decision=1)
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=100)])
        decisions = [
            _make_decision(0, 1, 50),
            _make_decision(0, 2, 25),
        ]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        # 1 COMMIT + 1 bucket × 2 decisions = 3 tokens
        assert len(tokens) == 3

    def test_capped_at_n_buckets(self) -> None:
        """If tokens_per_decision exceeds available buckets, cap at n_buckets."""
        cfg = MCTSConfig(
            use_token_variants=True,
            tokens_per_decision=99,
            ship_fraction_buckets=(0.5, 1.0),  # only 2 buckets
        )
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=100)])
        decisions = [_make_decision(0, 1, 50)]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        # 1 COMMIT + min(99, 2) = 3 tokens
        assert len(tokens) == 3


class TestBucketSelectionByDistance:
    def test_chosen_bucket_first_then_neighbors(self) -> None:
        """Buckets sorted by |bucket_value - chosen_fraction|. With buckets
        (0.25, 0.5, 0.75, 1.0) and ships=50/100=0.5, the order should be
        bucket 1 (0.5, dist 0) → bucket 0 (0.25, dist 0.25) or 2 (0.75, dist 0.25)
        → bucket 3 (1.0, dist 0.5)."""
        cfg = MCTSConfig(use_token_variants=True, tokens_per_decision=4)
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=100)])
        decisions = [_make_decision(src_id=0, target_id=1, ships=50)]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        # Skip COMMIT, look at the 4 launch tokens
        launch_tokens = tokens[1:]
        # First MUST be the chosen bucket (index 1, value 0.5)
        assert launch_tokens[0].ship_fraction_bucket == 1
        # The most-distant bucket (index 3, value 1.0, distance 0.5) is last
        assert launch_tokens[-1].ship_fraction_bucket == 3
        # The two middle slots are buckets 0 and 2 (both distance 0.25);
        # ordering between equidistant buckets is sort-stable on bucket index.
        assert {launch_tokens[1].ship_fraction_bucket, launch_tokens[2].ship_fraction_bucket} == {0, 2}

    def test_chosen_fraction_at_extreme(self) -> None:
        """ships=src.ships → fraction=1.0; bucket 3 (1.0) is chosen, bucket 0
        (0.25, distance 0.75) is last."""
        cfg = MCTSConfig(use_token_variants=True, tokens_per_decision=4)
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=100)])
        decisions = [_make_decision(0, 1, ships=100)]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        launch_tokens = tokens[1:]
        assert launch_tokens[0].ship_fraction_bucket == 3  # 1.0 nearest 1.0
        assert launch_tokens[-1].ship_fraction_bucket == 0  # 0.25 farthest from 1.0


class TestSourceFiltering:
    def test_decision_with_nonexistent_source_skipped(self) -> None:
        """If decide_with_decisions returns a decision whose src_id isn't in
        state, generator skips it defensively (shouldn't happen in real use,
        but better safe)."""
        cfg = MCTSConfig(use_token_variants=True, tokens_per_decision=2)
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=100)])
        decisions = [
            _make_decision(src_id=99, target_id=1, ships=50),  # src 99 doesn't exist
            _make_decision(src_id=0, target_id=2, ships=25),
        ]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        # COMMIT + 2 tokens for the valid decision
        assert len(tokens) == 3

    def test_decision_with_zero_ship_source_skipped(self) -> None:
        """If src.ships <= 0 (unlikely but defensive), skip the decision."""
        cfg = MCTSConfig(use_token_variants=True, tokens_per_decision=2)
        state = FakeState(planets=[FakePlanet(id=0, owner=0, ships=0)])
        decisions = [_make_decision(src_id=0, target_id=1, ships=10)]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        assert tokens == [LaunchToken.COMMIT]


class TestRankingPreservesDecisionOrder:
    def test_first_decision_tokens_come_before_second(self) -> None:
        """Decisions arrive ranked by heuristic; tokens preserve that order."""
        cfg = MCTSConfig(use_token_variants=True, tokens_per_decision=1)
        state = FakeState(planets=[
            FakePlanet(id=0, owner=0, ships=100),
            FakePlanet(id=5, owner=0, ships=100),
        ])
        decisions = [
            _make_decision(src_id=0, target_id=1, ships=50),
            _make_decision(src_id=5, target_id=2, ships=50),
        ]
        with ExitStack() as stack:
            for p in _patches(decisions):
                stack.enter_context(p)
            tokens = generate_ranked_tokens(state, 0, cfg)
        # Skip COMMIT — token from decision[0] (src=0) first, then from decision[1] (src=5)
        assert tokens[1].src_planet_id == 0
        assert tokens[2].src_planet_id == 5


class TestLongTailDisabledByDefault:
    def test_long_tail_off_returns_input_unchanged(self) -> None:
        cfg = MCTSConfig(use_token_variants=True, long_tail_enabled=False)
        state = FakeState(planets=[
            FakePlanet(id=0, owner=0, ships=100, x=0.0, y=0.0),
            FakePlanet(id=1, owner=1, ships=50, x=10.0, y=0.0),
        ])
        tokens = [LaunchToken.COMMIT, LaunchToken(0, 1, 1)]
        out = extend_with_long_tail(tokens, state, 0, cfg)
        assert out == tokens

    def test_long_tail_on_appends_unseen_combos(self) -> None:
        cfg = MCTSConfig(
            use_token_variants=True,
            long_tail_enabled=True,
            ship_fraction_buckets=(0.5, 1.0),  # 2 buckets
        )
        state = FakeState(planets=[
            FakePlanet(id=0, owner=0, ships=100, x=0.0, y=0.0),
            FakePlanet(id=1, owner=1, ships=50, x=10.0, y=0.0),
            FakePlanet(id=2, owner=-1, ships=20, x=20.0, y=0.0),
        ])
        # Prior already has (src=0, target=1, bucket=0)
        tokens = [LaunchToken.COMMIT, LaunchToken(0, 1, 0)]
        out = extend_with_long_tail(tokens, state, 0, cfg)
        # Long-tail adds: (0,1,1), (0,2,0), (0,2,1) — 3 new tokens
        # NOT (0,1,0) since it's already there. NOT (0,0,*) since target==src.
        assert len(out) == 2 + 3
        # Sorted by L2 distance ascending: (0,1,*) before (0,2,*); within
        # same target, bucket order is iteration order (0 then 1).
        new_keys = [(t.src_planet_id, t.target_planet_id, t.ship_fraction_bucket)
                    for t in out[2:]]
        assert (0, 1, 1) in new_keys
        assert (0, 2, 0) in new_keys
        assert (0, 2, 1) in new_keys
