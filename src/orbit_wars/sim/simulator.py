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
    # Toggle whether to skip phase 5 (rotation + sweep). True for Day 3-5
    # (phase unimplemented). Becomes False once real Phase 5 lands (Day 7-9).
    skip_phase_5: bool = True

    def step(
        self, state: SimState, actions: dict[int, list[Action]]
    ) -> SimState:
        """Apply one full env turn. Returns the next state.

        `actions` keys are player IDs (0-indexed). Missing players default to no actions.
        """
        new_state = deepcopy(state)
        new_state.step += 1

        self._phase_0_comet_expiration(new_state)
        if not self.skip_comet_spawn:
            self._phase_1_comet_spawn(new_state)
        # combat_lists carries arrivals from phase 4 + phase 5 into phase 6
        combat_lists: dict[int, list] = {p.id: [] for p in new_state.planets}
        self._phase_2_apply_actions(new_state, actions)
        self._phase_3_production(new_state)
        self._phase_4_advance_fleets(new_state, combat_lists)
        # Phase 5 (rotation + comet sweep) is unimplemented (Days 7-9).
        # For Day 3-5, real games have ~28 planets with most rotating —
        # the original "no rotating bodies" guard would only trigger for
        # synthetic test states. If skip_phase_5 is True (default), we
        # silently skip Phase 5 so step() works end-to-end on real
        # scenarios; planet x/y will diverge from env (state_diff doesn't
        # check x/y so this is fine for Day 3-5) but rotation-induced
        # fleet sweeps are NOT captured and will manifest as fleet-count
        # / ownership-flip divergence on long-running fleet states.
        if not self.skip_phase_5:
            self._phase_5_rotate_planets(new_state, combat_lists)
        self._phase_6_resolve_combat(new_state, combat_lists)

        return new_state

    def _has_rotating_bodies(self, state: SimState) -> bool:
        """True iff this state contains any planet that would rotate or any comets.

        Static planets (env L572): orbital_r + radius >= ROTATION_RADIUS_LIMIT (50).
        Originally intended as a Phase 5 short-circuit guard, but real games
        have ~28 planets with most rotating, so the guard tripped almost never.
        Replaced with the simpler skip_phase_5 flag. This helper retained for
        the Phase 5 stub regression test (test_phase_5_rotation_still_raises).
        """
        from orbit_wars.geometry import ROTATION_RADIUS_LIMIT, orbital_radius

        if state.comet_groups:
            return True
        for p in state.planets:
            if orbital_radius(p.x, p.y) + p.radius < ROTATION_RADIUS_LIMIT:
                return True
        return False

    # ------------------------------------------------------------------
    # Phases — stubs. Land per design doc Section 4 build order.
    # ------------------------------------------------------------------

    def _phase_0_comet_expiration(self, state: SimState) -> None:
        """env L419-439: drop comets where path_index >= len(path).

        Day 3-5 scenarios are filtered to exclude comets; this is a no-op
        for now. Real implementation lands Day 9-11. If a comet appears
        here despite the filter, the validator's diff will catch it under
        'comet-related'.
        """
        return

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
        """env L519-551: STUB. Detect in-flight fleets arriving THIS turn
        and push them into combat_lists. Does NOT advance fleet positions.

        Day 3-5 stub: borrows fleet ETA prediction from straight-line distance
        (safe for static planets only). Real Phase 4 (sun + planet collisions,
        position update, sweep) lands Day 5-7.
        """
        from orbit_wars.geometry import dist, fleet_speed
        from orbit_wars.world import ArrivalEvent

        remaining_fleets = []
        for fleet in state.fleets:
            target = state.planet_by_id(fleet.target_planet_id)
            if target is None:
                # Fleet has no resolved target (e.g., spawned this turn by
                # Phase 2 with target_planet_id=-1). Cannot compute ETA;
                # leave in flight, will be picked up next turn.
                remaining_fleets.append(fleet)
                continue
            speed = fleet_speed(fleet.ships)
            distance = dist(fleet.x, fleet.y, target.x, target.y)
            # ETA in TURNS rounded up; eta=1 means "arrives this turn"
            eta_turns = max(1, int((distance + speed - 1) / speed))
            if eta_turns <= 1:
                combat_lists.setdefault(target.id, []).append(
                    ArrivalEvent(eta=1, owner=fleet.owner, ships=fleet.ships)
                )
                # Fleet consumed
            else:
                # Stays in flight; Day 3-5 stub does NOT update position
                remaining_fleets.append(fleet)
        state.fleets = remaining_fleets

    def _phase_5_rotate_planets(
        self, state: SimState, combat_lists: dict[int, list]
    ) -> None:
        """env L553-627: rotate orbiting planets (r + radius < ROTATION_RADIUS_LIMIT);
        advance comet path_index; sweep_fleets for fleets caught by moving planets. Day 7-9."""
        raise NotImplementedError("Phase 5 (rotate + sweep) lands Day 7-9")

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
