"""MCTS forward-model simulator: deterministic env-faithful step function.

Per `docs/research_documents/mcts_forward_model_design.md` Section 3.2,
`Simulator.step(state, actions) -> state` mirrors the env's per-turn phase
order (env source `.venv/.../orbit_wars.py` L419-711):

    Phase 0 (env L419-439): comet expiration
    Phase 1 (env L441-477): comet spawn (NO-OP — see design doc Section 5 risk #2)
    Phase 2 (env L479-512): apply actions (validate + spawn fleets)
    Phase 3 (env L514-517): production
    Phase 4 (env L519-551): advance fleets, check sun + planet collisions
    Phase 5 (env L553-627): rotate planets + comet movement, sweep for fleets
    Phase 6 (env L630-669): combat resolution from combat_lists

Phase 7 (obs sync) and Phase 8 (termination/reward) are handled outside the
simulator (by the validator and by MCTS scoring respectively).

Build order (per design doc Section 4): minimal → fleet movement → rotation
→ comets. Each phase implementation lands separately, gated by the validator.

CURRENT STATE: scaffold. step() raises NotImplementedError. Phase methods land
on Days 3-11 per the design doc's build order.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .action import Action, validate_move
from .state import SimFleet, SimState

__all__ = ["Simulator"]


@dataclass(slots=True)
class Simulator:
    """Deterministic env-faithful forward model.

    Stateless apart from configuration; `step()` takes state in and returns a
    fresh state (deepcopied internally so callers can keep the input).
    """

    # Toggle whether to skip phase 1 (comet spawn). Should be True (the env's
    # comet spawn uses RNG we can't reproduce — see design doc Section 5 risk #2).
    skip_comet_spawn: bool = True

    def step(
        self, state: SimState, actions: dict[int, list[Action]]
    ) -> SimState:
        """Apply one full env turn. Returns the next state.

        `actions` keys are player IDs (0-indexed). Missing players default to no actions.
        """
        new_state = deepcopy(state)

        self._phase_0_comet_expiration(new_state)
        if not self.skip_comet_spawn:
            self._phase_1_comet_spawn(new_state)
        # combat_lists carries arrivals from phase 4 + phase 5 into phase 6
        combat_lists: dict[int, list] = {p.id: [] for p in new_state.planets}
        self._phase_2_apply_actions(new_state, actions)
        self._phase_3_production(new_state)
        self._phase_4_advance_fleets(new_state, combat_lists)
        self._phase_5_rotate_planets(new_state, combat_lists)
        self._phase_6_resolve_combat(new_state, combat_lists)

        # Step increments LAST (matches env semantics: env reads obs.step
        # for Phase 5 rotation BEFORE incrementing; see env L555).
        new_state.step += 1
        return new_state


    # ------------------------------------------------------------------
    # Phases — stubs. Land per design doc Section 4 build order.
    # ------------------------------------------------------------------

    def _phase_0_comet_expiration(self, state: SimState) -> None:
        """env L419-439: drop comets where path_index >= len(path).

        For each comet group, identify planet_ids whose path_index has
        reached path length (path consumed). Remove those from:
          - state.planets
          - state.initial_planets
          - state.comet_groups[*].planet_ids
          - empty groups themselves
        """
        expired_pids: set[int] = set()
        for group in state.comet_groups:
            for i, pid in enumerate(group.planet_ids):
                if group.path_index >= len(group.paths[i]):
                    expired_pids.add(pid)

        if not expired_pids:
            return

        state.planets = [p for p in state.planets if p.id not in expired_pids]
        state.initial_planets = [
            p for p in state.initial_planets if p.id not in expired_pids
        ]
        for group in state.comet_groups:
            group.planet_ids = [
                pid for pid in group.planet_ids if pid not in expired_pids
            ]
        state.comet_groups = [g for g in state.comet_groups if g.planet_ids]

    def _phase_1_comet_spawn(self, state: SimState) -> None:
        """env L441-477: spawn at COMET_SPAWN_STEPS=[50,150,250,350,450].
        DEFAULT IS NO-OP — see design doc Section 5 risk #2."""
        raise NotImplementedError(
            "Phase 1 (comet spawn) is intentionally no-op by default. "
            "If you need spawn simulation, you must reproduce the env's RNG state."
        )

    def _phase_2_apply_actions(
        self, state: SimState, actions: dict[int, list[Action]]
    ) -> None:
        """env L479-512: validate each move, spawn accepted fleets, increment next_fleet_id.

        Process players in ascending player_id order so fleet IDs are stable
        across runs (matches env behavior — env iterates players in fixed
        order per env L479). Per env L497-499, fleets spawn just OUTSIDE
        the source planet (planet.radius + LAUNCH_CLEARANCE=0.1) so they
        don't immediately collide with their origin in Phase 4.
        """
        import math

        for player_id in sorted(actions):
            for action in actions[player_id]:
                if not validate_move(state, player_id, action):
                    continue
                src = state.planet_by_id(action.from_planet_id)
                # validate_move guarantees src is non-None and player-owned
                assert src is not None
                clearance = src.radius + 0.1  # env LAUNCH_CLEARANCE
                fleet = SimFleet(
                    id=state.next_fleet_id,
                    owner=player_id,
                    from_planet_id=src.id,
                    target_planet_id=-1,        # derived later by Phase 4 if needed
                    x=src.x + math.cos(action.angle) * clearance,
                    y=src.y + math.sin(action.angle) * clearance,
                    angle=action.angle,
                    ships=action.ships,
                    spawned_at_step=state.step,
                )
                state.fleets.append(fleet)
                state.next_fleet_id += 1
                src.ships -= action.ships

    def _phase_3_production(self, state: SimState) -> None:
        """env L514-517: planet.ships += planet.production for owner != -1."""
        for p in state.planets:
            if p.owner != -1:
                p.ships += p.production

    def _phase_4_advance_fleets(
        self, state: SimState, combat_lists: dict[int, list]
    ) -> None:
        """env L519-551: advance each fleet by speed; remove on OOB, sun
        collision, or planet collision (continuous via point-to-segment).

        For each fleet, in env iteration order:
          1. Update position by (cos(angle), sin(angle)) * fleet_speed(ships)
          2. If new position is outside [0, BOARD_SIZE]^2 → remove (no combat)
          3. If segment from old→new passes within SUN_RADIUS of sun → remove
          4. Iterate planets IN ORDER: if segment passes within planet.radius
             of any planet, push ArrivalEvent to combat_lists[that planet.id],
             remove the fleet, and BREAK (first match wins, per env L549)
          5. Otherwise survive with updated position
        """
        import math
        from orbit_wars.geometry import (
            BOARD_SIZE,
            SUN_CENTER,
            SUN_RADIUS,
            fleet_speed,
            point_to_segment_distance,
        )
        from orbit_wars.world import ArrivalEvent

        remaining_fleets = []
        for fleet in state.fleets:
            speed = fleet_speed(fleet.ships)
            old_pos = (fleet.x, fleet.y)
            new_x = fleet.x + math.cos(fleet.angle) * speed
            new_y = fleet.y + math.sin(fleet.angle) * speed
            new_pos = (new_x, new_y)

            # Out-of-bounds: removed silently (no combat).
            if not (0 <= new_x <= BOARD_SIZE and 0 <= new_y <= BOARD_SIZE):
                continue

            # Sun collision: removed silently (no combat).
            if point_to_segment_distance(SUN_CENTER, old_pos, new_pos) < SUN_RADIUS:
                continue

            # Planet collision (any planet on path) — first match wins.
            collided = False
            for planet in state.planets:
                planet_pos = (planet.x, planet.y)
                if point_to_segment_distance(planet_pos, old_pos, new_pos) < planet.radius:
                    combat_lists.setdefault(planet.id, []).append(
                        ArrivalEvent(eta=1, owner=fleet.owner, ships=fleet.ships)
                    )
                    collided = True
                    break

            if collided:
                continue

            # Survived: commit new position.
            fleet.x = new_x
            fleet.y = new_y
            remaining_fleets.append(fleet)
        state.fleets = remaining_fleets

    def _phase_5_rotate_planets(
        self, state: SimState, combat_lists: dict[int, list]
    ) -> None:
        """env L553-627: rotate orbiting planets and sweep fleets caught in arc.

        For each non-comet planet:
          - Compute initial radius r and initial_angle from initial_planets
          - If r + radius < ROTATION_RADIUS_LIMIT: rotate to
              new_pos = CENTER + r * (cos(initial_angle + ang_vel * step),
                                      sin(initial_angle + ang_vel * step))
          - sweep_fleets(planet, old_pos, new_pos) — if old==new, no-op;
            else for each fleet not yet swept this turn, check if fleet's
            position is within planet.radius of the swept segment; if so,
            push to combat_lists[planet.id] and mark fleet swept

        Comet movement (env L592-611) is NOT handled here — Day 9-11 work.
        """
        import math
        from orbit_wars.geometry import ROTATION_RADIUS_LIMIT, SUN_CENTER, point_to_segment_distance
        from orbit_wars.world import ArrivalEvent

        initial_by_id = {p.id: p for p in state.initial_planets}
        swept_fleet_ids: set[int] = set()

        for planet in state.planets:
            if planet.is_comet:
                continue
            initial_p = initial_by_id.get(planet.id)
            if initial_p is None:
                continue

            dx = initial_p.x - SUN_CENTER[0]
            dy = initial_p.y - SUN_CENTER[1]
            r = math.sqrt(dx * dx + dy * dy)
            old_pos = (planet.x, planet.y)

            if r + planet.radius < ROTATION_RADIUS_LIMIT:
                initial_angle = math.atan2(dy, dx)
                current_angle = initial_angle + state.angular_velocity * state.step
                planet.x = SUN_CENTER[0] + r * math.cos(current_angle)
                planet.y = SUN_CENTER[1] + r * math.sin(current_angle)

            new_pos = (planet.x, planet.y)

            # sweep_fleets — env L559-568
            if old_pos == new_pos:
                continue
            for fleet in state.fleets:
                if fleet.id in swept_fleet_ids:
                    continue
                if point_to_segment_distance((fleet.x, fleet.y), old_pos, new_pos) < planet.radius:
                    combat_lists.setdefault(planet.id, []).append(
                        ArrivalEvent(eta=1, owner=fleet.owner, ships=fleet.ships)
                    )
                    swept_fleet_ids.add(fleet.id)

        # Comet movement along pre-computed paths — env L592-611.
        # Comets share the swept_fleet_ids set with planet rotation, so a
        # fleet swept by a planet is not also swept by a comet.
        expired_comet_pids: set[int] = set()
        for group in state.comet_groups:
            group.path_index += 1
            idx = group.path_index
            for i, pid in enumerate(group.planet_ids):
                planet = state.planet_by_id(pid)
                if planet is None:
                    continue
                p_path = group.paths[i]
                if idx >= len(p_path):
                    expired_comet_pids.add(pid)
                    continue
                old_pos = (planet.x, planet.y)
                planet.x = p_path[idx][0]
                planet.y = p_path[idx][1]
                # Skip sweep on first placement (off-board placeholder x=-99)
                if old_pos[0] < 0:
                    continue
                new_pos = (planet.x, planet.y)
                if old_pos == new_pos:
                    continue
                for fleet in state.fleets:
                    if fleet.id in swept_fleet_ids:
                        continue
                    if point_to_segment_distance((fleet.x, fleet.y), old_pos, new_pos) < planet.radius:
                        combat_lists.setdefault(planet.id, []).append(
                            ArrivalEvent(eta=1, owner=fleet.owner, ships=fleet.ships)
                        )
                        swept_fleet_ids.add(fleet.id)

        # Remove expired comets — same pattern as Phase 0 (env L605-611).
        if expired_comet_pids:
            state.planets = [p for p in state.planets if p.id not in expired_comet_pids]
            state.initial_planets = [
                p for p in state.initial_planets if p.id not in expired_comet_pids
            ]
            for group in state.comet_groups:
                group.planet_ids = [
                    pid for pid in group.planet_ids if pid not in expired_comet_pids
                ]
            state.comet_groups = [g for g in state.comet_groups if g.planet_ids]

        if swept_fleet_ids:
            state.fleets = [f for f in state.fleets if f.id not in swept_fleet_ids]

    def _phase_6_resolve_combat(
        self, state: SimState, combat_lists: dict[int, list]
    ) -> None:
        """env L630-669: per planet, group arrivals by owner; top-2 cancel; survivor fights garrison.

        Reuses world.resolve_arrival_event for the actual combat math.
        """
        from orbit_wars.world import resolve_arrival_event

        for planet in state.planets:
            arrivals = combat_lists.get(planet.id, [])
            if not arrivals:
                continue
            new_owner, new_ships = resolve_arrival_event(
                planet.owner, planet.ships, arrivals,
            )
            planet.owner = new_owner
            planet.ships = new_ships
