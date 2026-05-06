"""Token sequence → env-format actions, with intercept-aware angle computation.

Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md §4.6, §5.3.

A token is `(src_planet_id, target_planet_id, ship_fraction_bucket)` plus the
COMMIT sentinel. To convert a sequence of picks into the env-format action
list `list[list[float|int]]` the simulator expects, this module:

  1. Resolves each token's `ship_fraction_bucket` against the player's CURRENT
     planet ships at decision time, accounting for prior intra-turn deductions
     (so two tokens picking from the same source planet decrement correctly).
  2. Computes the angle by mirroring the heuristic's intercept logic — straight
     `safe_angle_and_distance` for static targets, `aim_with_prediction` for
     orbiting planets and comets. Same ships count → same angle as heuristic.
  3. Validates the resulting Action via `validate_move`. Invalid actions are
     SILENTLY DROPPED, mirroring env L482-491. The token effectively becomes a
     no-op for that player's turn.

Critical correctness contract (Risk 2 in the design doc):
  For a token `(src, target, bucket)` whose bucket-resolved ships equal the
  ships count chosen by the heuristic for `(src, target)` at the same state,
  the serialized angle MUST match the heuristic's emitted angle within a
  small tolerance. If this contract breaks, every MCTS evaluation is
  computed against a phantom version of the game and the search learns
  nothing useful.
"""

from __future__ import annotations

from typing import Iterable

from orbit_wars.geometry import is_static_planet, safe_angle_and_distance
from orbit_wars.sim.action import Action, validate_move
from orbit_wars.sim.state import SimPlanet, SimState
from orbit_wars.world import aim_with_prediction

from .config import MCTSConfig
from .token import LaunchToken

__all__ = ["compute_angle_for_target", "serialize_picks_to_env_actions"]


def _is_comet_planet(state: SimState, planet_id: int) -> bool:
    """True iff `planet_id` belongs to any active comet group."""
    for group in state.comet_groups:
        if planet_id in group.planet_ids:
            return True
    return False


def _comet_path_and_index(
    state: SimState, planet_id: int
) -> tuple[list[tuple[float, float]] | None, int]:
    """Return (path, current_path_index) for a comet planet, or (None, 0)."""
    for group in state.comet_groups:
        if planet_id not in group.planet_ids:
            continue
        idx_in_group = group.planet_ids.index(planet_id)
        return group.paths[idx_in_group], group.path_index
    return None, 0


def compute_angle_for_target(
    state: SimState,
    src_id: int,
    target_id: int,
    ships: int,
) -> float | None:
    """Return the launch angle from `src_id` to `target_id` for a fleet of
    `ships` ships, or None if no sun-safe shot exists.

    Mirrors the heuristic's per-launch angle logic in
    ``heuristic.strategy._plan_launch`` so that for the same (src, target,
    ships) on the same state, the angle matches. The heuristic's logic:

      - Static targets (orbital_radius + radius >= ROTATION_RADIUS_LIMIT
        AND not a comet): straight `safe_angle_and_distance` aim.
      - Moving targets (orbiting planet OR comet): `aim_with_prediction`
        intercept solver.

    Returns the angle in radians, or None if the path is sun-blocked /
    intercept-impossible / target left the board (for comets).

    Cost: one geometry call (~µs) for static; up to 5 intercept iterations
    (~tens of µs) for moving. Cheap enough to call per token at serialization.
    """
    src = state.planet_by_id(src_id)
    target = state.planet_by_id(target_id)
    if src is None or target is None:
        return None

    is_comet = _is_comet_planet(state, target_id)
    target_is_static = (
        is_static_planet(target.x, target.y, target.radius) and not is_comet
    )

    if target_is_static:
        # Straight-line aim — no intercept needed (target doesn't move).
        result = safe_angle_and_distance(
            src.x, src.y, src.radius,
            target.x, target.y, target.radius,
        )
        if result is None:
            return None
        angle, _hit_distance = result
        return float(angle)

    # Moving target — intercept solver.
    # Per design §5.3 / aim_with_prediction docstring: `initial` is unused but
    # must be truthy to trigger the moving-target loop for orbiting planets.
    # Pass the target itself as `initial` (any non-None value works).
    initial: SimPlanet | None = target if not is_comet else None
    comet_path, comet_idx = _comet_path_and_index(state, target_id) if is_comet else (None, 0)

    intercept = aim_with_prediction(
        src=src,
        target=target,
        ships=ships,
        initial=initial,
        angular_velocity=state.angular_velocity,
        comet_path=comet_path,
        comet_path_index=comet_idx,
    )
    if intercept is None:
        return None
    angle, _eta, _predicted_xy = intercept
    return float(angle)


def serialize_picks_to_env_actions(
    picks_per_player: dict[int, list[int]],
    ranked_tokens_per_player: dict[int, list[LaunchToken]],
    state: SimState,
    cfg: MCTSConfig,
) -> dict[int, list[Action]]:
    """Convert each player's token-index sequence into validated env Actions.

    Args:
        picks_per_player: ``{player_id: [token_idx_0, token_idx_1, ...]}``.
            Each token_idx indexes into ``ranked_tokens_per_player[player_id]``.
            COMMIT tokens (or any token whose serialization fails) are skipped.
        ranked_tokens_per_player: ``{player_id: [LaunchToken, ...]}`` from
            :func:`tokens.generate_ranked_tokens`.
        state: the SimState at THIS env-turn (BEFORE applying any picks; ship
            counts read from here are the player's pre-turn pool).
        cfg: MCTSConfig — used for `ship_fraction_buckets`.

    Returns:
        ``{player_id: [Action, ...]}``. Missing players (no picks, or all picks
        invalid) get an empty list.

    Invalid-token handling: silently drops the token and continues with the
    next pick. Mirrors env L482-491 (the env silently rejects malformed
    actions). This is intentional — MCTS learns the consequence of including
    an invalid token (it becomes a no-op, wasting the pick slot).

    Ship-pool bookkeeping: each player has a fresh pool initialized from
    `state.planets` (ships per owned planet). When a token launches `n`
    ships from `src`, the pool is decremented by `n`. Subsequent tokens
    from the same `src` see the reduced pool.
    """
    env_actions: dict[int, list[Action]] = {}

    for player_id, token_indices in picks_per_player.items():
        actions: list[Action] = []
        # Per-player ship pool initialized from owned planets at THIS state.
        ship_pool: dict[int, int] = {
            p.id: int(p.ships)
            for p in state.planets
            if p.owner == player_id
        }
        ranked = ranked_tokens_per_player.get(player_id, [])

        for token_idx in token_indices:
            if token_idx < 0 or token_idx >= len(ranked):
                continue  # invalid index — defensive
            token = ranked[token_idx]
            if token.is_commit():
                # Commit signals "stop launching this turn" — break out of the
                # loop entirely (any later picks for this player are ignored).
                break

            available = ship_pool.get(token.src_planet_id, 0)
            if available <= 0:
                # Source planet not owned (or out of ships) — skip.
                continue

            fraction = cfg.ship_fraction_buckets[token.ship_fraction_bucket]
            ships = max(1, int(available * fraction))
            if ships > available:
                # Numerical edge case (fraction > 1.0 or rounding issue) —
                # cap at available.
                ships = available
            if ships <= 0:
                continue

            angle = compute_angle_for_target(
                state, token.src_planet_id, token.target_planet_id, ships
            )
            if angle is None:
                # Sun-blocked / intercept-impossible — silently skip.
                continue

            action = Action(
                from_planet_id=token.src_planet_id,
                angle=angle,
                ships=ships,
            )
            if not validate_move(state, player_id, action):
                continue

            actions.append(action)
            ship_pool[token.src_planet_id] = available - ships

        env_actions[player_id] = actions

    return env_actions


def serialize_picks_for_env(
    picks_per_player: dict[int, list[int]],
    ranked_tokens_per_player: dict[int, list[LaunchToken]],
    state: SimState,
    cfg: MCTSConfig,
) -> dict[int, list[list[float | int]]]:
    """Like :func:`serialize_picks_to_env_actions` but returns the env's raw
    `[[from_id, angle, ships], ...]` shape ready to pass to ``Simulator.step``
    or ``env.step``. Convenience wrapper — most callers want the typed Action
    form for further validation/manipulation, but the env interface is raw.
    """
    actions_per_player = serialize_picks_to_env_actions(
        picks_per_player, ranked_tokens_per_player, state, cfg
    )
    return {
        player_id: [a.to_env_format() for a in actions]
        for player_id, actions in actions_per_player.items()
    }
