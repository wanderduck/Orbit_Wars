"""Unit tests for LaunchToken + token_id encoding (Phase 1 of option 2).

Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md §2.1, §4.1.
"""
from __future__ import annotations

import pytest

from orbit_wars.mcts.token import LaunchToken, token_id


class TestLaunchTokenEquality:
    def test_same_fields_equal(self) -> None:
        a = LaunchToken(src_planet_id=3, target_planet_id=7, ship_fraction_bucket=2)
        b = LaunchToken(src_planet_id=3, target_planet_id=7, ship_fraction_bucket=2)
        assert a == b
        assert hash(a) == hash(b)

    def test_different_fields_unequal(self) -> None:
        a = LaunchToken(3, 7, 2)
        assert a != LaunchToken(4, 7, 2)
        assert a != LaunchToken(3, 8, 2)
        assert a != LaunchToken(3, 7, 1)

    def test_frozen_immutable(self) -> None:
        a = LaunchToken(3, 7, 2)
        with pytest.raises((AttributeError, Exception)):
            a.src_planet_id = 99  # type: ignore[misc]


class TestCommitSentinel:
    def test_commit_is_singleton_accessor(self) -> None:
        # The accessor is the same object across calls
        assert LaunchToken.COMMIT is LaunchToken.COMMIT

    def test_commit_has_negative_fields(self) -> None:
        assert LaunchToken.COMMIT.src_planet_id == -1
        assert LaunchToken.COMMIT.target_planet_id == -1
        assert LaunchToken.COMMIT.ship_fraction_bucket == -1

    def test_is_commit_predicate_true_for_commit(self) -> None:
        assert LaunchToken.COMMIT.is_commit() is True

    def test_is_commit_predicate_false_for_real_token(self) -> None:
        assert LaunchToken(0, 0, 0).is_commit() is False
        assert LaunchToken(5, 10, 3).is_commit() is False

    def test_is_commit_only_checks_src(self) -> None:
        """is_commit() short-circuits on src_planet_id == -1. A token with
        src=-1 but other-real-fields would still register as commit-like;
        this is intentional — the sentinel is the unique src=-1 token."""
        # Sanity: any token with src=-1 reads as commit (we never construct
        # real tokens with src=-1; planets have id >= 0).
        weird = LaunchToken(-1, 5, 2)
        assert weird.is_commit() is True


class TestTokenIdEncoding:
    def test_commit_encodes_to_zero(self) -> None:
        assert token_id(LaunchToken.COMMIT) == 0

    def test_commit_with_explicit_negatives_encodes_to_zero(self) -> None:
        assert token_id(LaunchToken(-1, -1, -1)) == 0

    def test_zero_indexed_token_encodes_above_zero(self) -> None:
        """A real token with src=0, target=0, bucket=0 must NOT collide with
        COMMIT's id of 0. The +1 offset in the encoding handles this."""
        tok = LaunchToken(src_planet_id=0, target_planet_id=0, ship_fraction_bucket=0)
        assert token_id(tok) != 0
        # Specifically: ((0+1)<<20) | ((0+1)<<8) | (0+1) = 0x100101
        assert token_id(tok) == (1 << 20) | (1 << 8) | 1

    def test_encoding_is_bijective_in_supported_range(self) -> None:
        """Different (src, target, bucket) triples must encode to different ids
        within the supported planet/bucket range (planet ids 0-4094, buckets 0-253).
        """
        seen = set()
        for src in range(0, 30):
            for target in range(0, 30):
                for bucket in range(0, 4):
                    tid = token_id(LaunchToken(src, target, bucket))
                    assert tid not in seen, (
                        f"Collision at (src={src}, target={target}, bucket={bucket})"
                    )
                    seen.add(tid)
        # 30*30*4 = 3600 unique tokens encoded into 3600 unique ids
        assert len(seen) == 3600

    def test_encoding_supports_high_planet_ids(self) -> None:
        """Encoding header uses 12 bits for planet ids → support up to 4095."""
        tok = LaunchToken(src_planet_id=100, target_planet_id=200, ship_fraction_bucket=3)
        tid = token_id(tok)
        # Verify decoding by hand
        assert (tid >> 20) == 101  # src+1
        assert ((tid >> 8) & 0xFFF) == 201  # target+1
        assert (tid & 0xFF) == 4  # bucket+1
