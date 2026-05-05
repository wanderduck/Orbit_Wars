"""Action representation for the MCTS forward-model simulator.

The kaggle_environments env accepts player actions as a list of moves, where
each move is `[from_planet_id, angle_radians, ships]` (env L488). This module
provides typed wrappers and the env's validation rules (env L479-512).

See `docs/research_documents/mcts_forward_model_design.md` Section 3.3
quirk #11 — invalid actions are silently rejected.
"""

from __future__ import annotations

from dataclasses import dataclass

from .state import SimState

__all__ = ["Action", "validate_move"]


@dataclass(frozen=True, slots=True)
class Action:
    """One fleet launch."""

    from_planet_id: int
    angle: float                     # radians
    ships: int

    def to_env_format(self) -> list[float | int]:
        """Convert to the env's `[from_id, angle, ships]` list shape."""
        return [self.from_planet_id, float(self.angle), int(self.ships)]

    @classmethod
    def from_env_format(cls, move: list[float | int]) -> Action:
        """Parse the env's `[from_id, angle, ships]` list. Raises ValueError on bad shape."""
        if not isinstance(move, list) or len(move) != 3:
            raise ValueError(f"Move must be a 3-element list; got {move!r}")
        from_id, angle, ships = move
        return cls(int(from_id), float(angle), int(ships))


def validate_move(state: SimState, player_id: int, action: Action) -> bool:
    """Mirror the env's L482-491 validation. Returns True iff the move would be accepted.

    The env silently rejects invalid moves with no error/penalty. Five checks in order:
    1. Source planet exists.
    2. Source planet is owned by the player.
    3. Source planet has >= ships ships.
    4. Ships count is positive.
    (Action shape — list of 3 — is enforced by `Action.from_env_format`.)
    """
    src = state.planet_by_id(action.from_planet_id)
    if src is None:
        return False
    if src.owner != player_id:
        return False
    if action.ships <= 0:
        return False
    if src.ships < action.ships:
        return False
    return True
