"""Unit tests for SubNode + token-aware MCTSNode (Phase 4 of option 2).

Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md §4.2.
"""
from __future__ import annotations

import pytest

from orbit_wars.mcts.node_tokens import (
    MCTSNode,
    SubNode,
    canonicalize_committed,
    make_subnode_key,
)
from orbit_wars.sim.state import SimConfig, SimPlanet, SimState


def _state() -> SimState:
    """Minimal SimState for MCTSNode construction. Only owner-distribution
    matters for these tests; the rest of the state is empty."""
    return SimState(
        config=SimConfig(num_agents=2),
        step=0,
        planets=[
            SimPlanet(id=0, x=10, y=10, radius=4, owner=0, ships=100, production=5),
            SimPlanet(id=1, x=90, y=90, radius=4, owner=1, ships=80, production=5),
        ],
        fleets=[],
        comet_groups=[],
        initial_planets=[],
        angular_velocity=0.0,
        next_fleet_id=0,
    )


class TestSubNodeStats:
    def test_unvisited_pick_returns_zero_stats(self) -> None:
        sub = SubNode(picks_per_player=((), ()), committed_per_player=(False, False))
        assert sub.get_stat(player_idx=0, token_idx=5) == (0, 0.0)
        assert sub.get_stat(player_idx=1, token_idx=99) == (0, 0.0)

    def test_update_stat_accumulates(self) -> None:
        sub = SubNode(picks_per_player=((), ()), committed_per_player=(False, False))
        sub.update_stat(player_idx=0, token_idx=3, value=0.7)
        sub.update_stat(player_idx=0, token_idx=3, value=0.3)
        sub.update_stat(player_idx=0, token_idx=5, value=0.5)
        assert sub.get_stat(0, 3) == (2, 1.0)
        assert sub.get_stat(0, 5) == (1, 0.5)

    def test_stats_are_per_player(self) -> None:
        """Player 0's stats and player 1's stats live in separate buckets."""
        sub = SubNode(picks_per_player=((), ()), committed_per_player=(False, False))
        sub.update_stat(player_idx=0, token_idx=3, value=0.6)
        sub.update_stat(player_idx=1, token_idx=3, value=0.4)
        assert sub.get_stat(0, 3) == (1, 0.6)
        assert sub.get_stat(1, 3) == (1, 0.4)


class TestSubNodeAllCommitted:
    def test_all_false_initially(self) -> None:
        sub = SubNode(picks_per_player=((), ()), committed_per_player=(False, False))
        assert sub.all_committed is False

    def test_partial_commit_not_all(self) -> None:
        sub = SubNode(picks_per_player=((1,), ()), committed_per_player=(False, True))
        assert sub.all_committed is False

    def test_all_true_means_committed(self) -> None:
        sub = SubNode(picks_per_player=((1,), (2,)), committed_per_player=(True, True))
        assert sub.all_committed is True

    def test_single_player(self) -> None:
        sub = SubNode(picks_per_player=((),), committed_per_player=(True,))
        assert sub.all_committed is True


class TestSubNodeKeyCanonicalization:
    def test_key_is_hashable(self) -> None:
        key = make_subnode_key(picks_per_player=((1, 2), (3,)),
                               committed_per_player=(False, True))
        # Hashing should not raise — required for dict use
        hash(key)

    def test_same_inputs_produce_same_key(self) -> None:
        k1 = make_subnode_key(((1, 2), (3,)), (False, True))
        k2 = make_subnode_key(((1, 2), (3,)), (False, True))
        assert k1 == k2
        assert hash(k1) == hash(k2)

    def test_pick_order_matters(self) -> None:
        """Two different orderings of the same picks should produce DIFFERENT
        keys — the design uses ordered tuples, not frozensets."""
        k_order_a = make_subnode_key(((1, 2), ()), (False, False))
        k_order_b = make_subnode_key(((2, 1), ()), (False, False))
        assert k_order_a != k_order_b

    def test_commit_difference_matters(self) -> None:
        k_uncommitted = make_subnode_key(((1,), ()), (False, False))
        k_committed = make_subnode_key(((1,), ()), (True, False))
        assert k_uncommitted != k_committed


class TestCanonicalizeCommitted:
    def test_returns_picks_unchanged(self) -> None:
        """canonicalize_committed is the identity function — order matters,
        no frozensets. The wrapper exists for type clarity / future extension."""
        picks = ((1, 5, 3), (2,))
        out = canonicalize_committed(picks)
        assert out == picks

    def test_different_orderings_distinct(self) -> None:
        a = canonicalize_committed(((1, 2), ()))
        b = canonicalize_committed(((2, 1), ()))
        assert a != b


class TestMCTSNodeRootSubnode:
    def test_first_call_creates_subnode(self) -> None:
        node = MCTSNode(state=_state())
        sub = node.root_subnode(alive_players=[0, 1])
        assert sub.picks_per_player == ((), ())
        assert sub.committed_per_player == (False, False)
        assert sub.visits == 0

    def test_repeat_call_returns_same_object(self) -> None:
        """Subnode cache means repeated calls return the SAME instance —
        critical for stats accumulation across iterations."""
        node = MCTSNode(state=_state())
        sub_a = node.root_subnode(alive_players=[0, 1])
        sub_b = node.root_subnode(alive_players=[0, 1])
        assert sub_a is sub_b

    def test_alive_players_size_affects_arity(self) -> None:
        """A 4-player game's root subnode has 4-tuples, not 2-tuples."""
        node = MCTSNode(state=_state())
        sub = node.root_subnode(alive_players=[0, 1, 2, 3])
        assert sub.picks_per_player == ((), (), (), ())
        assert sub.committed_per_player == (False, False, False, False)

    def test_subnode_cache_separate_per_arity(self) -> None:
        """Calling root_subnode with different alive sets caches separately
        — correct because the keys differ in tuple length."""
        node = MCTSNode(state=_state())
        sub2 = node.root_subnode(alive_players=[0, 1])
        sub4 = node.root_subnode(alive_players=[0, 1, 2, 3])
        assert sub2 is not sub4
        assert sub2.picks_per_player != sub4.picks_per_player


class TestMCTSNodeFieldsInitialEmpty:
    def test_visits_zero(self) -> None:
        node = MCTSNode(state=_state())
        assert node.visits == 0

    def test_ranked_tokens_empty_dict(self) -> None:
        node = MCTSNode(state=_state())
        assert node.ranked_tokens == {}

    def test_children_empty_dict(self) -> None:
        node = MCTSNode(state=_state())
        assert node.children == {}

    def test_subnode_cache_empty_until_root_called(self) -> None:
        node = MCTSNode(state=_state())
        assert node.subnode_cache == {}
        node.root_subnode([0, 1])
        assert len(node.subnode_cache) == 1
