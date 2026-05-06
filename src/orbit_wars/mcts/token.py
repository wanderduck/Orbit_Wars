"""LaunchToken — atomic action element for the option-2 single-launch action space.

Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md §2.1, §4.1:

A token represents ONE launch decision: source planet, target planet, and a
discretized ship fraction. The agent's per-turn action is composed of an
ORDERED SEQUENCE of tokens (chosen at successive depths in the per-env-turn
sub-tree) terminated by the COMMIT sentinel.

Angle is NOT in the token. It's resolved at serialization time by re-running
the heuristic's intercept calculation on the live state. Per design §5.3:
encoding angle would explode cardinality 360× and force premature ETA
commitment for moving targets (orbiting planets, comets) where ETA depends
on ships → speed.

The COMMIT sentinel signals "no more launches this env-turn — advance the
simulator". Selecting it as the next sub-tree pick triggers Simulator.step().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

__all__ = ["LaunchToken", "token_id"]


@dataclass(frozen=True, slots=True)
class LaunchToken:
    """One atomic launch decision.

    Fields:
        src_planet_id: owned planet id (must own at decision time; -1 for COMMIT)
        target_planet_id: any planet id (enemy/neutral/comet/own); -1 for COMMIT
        ship_fraction_bucket: index into MCTSConfig.ship_fraction_buckets;
            -1 for COMMIT. Resolved against src.ships at serialization time
            (see serialize.py — accounts for prior intra-turn deductions).

    Equality and hashing use all three fields. Two tokens with identical
    (src, target, bucket) compare equal regardless of when they were created;
    this matters because the search uses tokens as dict keys for sub-node
    stats and child-state lookup.

    The COMMIT sentinel is accessed as `LaunchToken.COMMIT` and tests via
    `token.is_commit()`. Both are O(1) — no string comparison.
    """

    src_planet_id: int
    target_planet_id: int
    ship_fraction_bucket: int

    # Singleton sentinel — class attribute, populated below the class definition.
    # Mypy/ty can't see assignment-after-class-body, so declare via ClassVar.
    COMMIT: ClassVar["LaunchToken"]

    def is_commit(self) -> bool:
        """True iff this token is the COMMIT sentinel.

        Cheaper than equality comparison against `LaunchToken.COMMIT` because
        we only check src_planet_id (the COMMIT sentinel is the unique token
        with a negative src_planet_id; real planets have id >= 0).
        """
        return self.src_planet_id == -1


# Populate the COMMIT sentinel. -1 for all fields makes it
# unambiguously distinguishable from any real token (real planet ids are >= 0,
# real bucket indices are >= 0).
LaunchToken.COMMIT = LaunchToken(
    src_planet_id=-1, target_planet_id=-1, ship_fraction_bucket=-1
)


def token_id(token: LaunchToken) -> int:
    """Stable integer encoding for use as a dict key.

    Layout (LSB → MSB):
      bits 0-7   = ship_fraction_bucket + 1   (0 reserved for COMMIT)
      bits 8-19  = target_planet_id + 1       (0 reserved for COMMIT)
      bits 20-31 = src_planet_id + 1          (0 reserved for COMMIT)

    Supports planet ids up to 4095 and bucket indices up to 254 — well above
    any plausible game configuration.

    The COMMIT sentinel always encodes to 0; this is the canonical "no token"
    or "stop launching" key used in sub-node stats dicts.

    Encoding is bijective on (src_planet_id, target_planet_id, ship_fraction_bucket)
    in the supported range — caller can use this as a hash key without collision
    concerns within a single episode.
    """
    if token.is_commit():
        return 0
    return (
        ((token.src_planet_id + 1) << 20)
        | ((token.target_planet_id + 1) << 8)
        | (token.ship_fraction_bucket + 1)
    )
