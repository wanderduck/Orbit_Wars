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

from .action import Action
from .state import SimState

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
        new_state.step += 1

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

        return new_state

    # ------------------------------------------------------------------
    # Phases — stubs. Land per design doc Section 4 build order.
    # ------------------------------------------------------------------

    def _phase_0_comet_expiration(self, state: SimState) -> None:
        """env L419-439: drop comets where path_index >= len(path). Day 9-11."""
        raise NotImplementedError("Phase 0 (comet expiration) lands Day 9-11")

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
        """env L479-512: validate each move, spawn accepted fleets, increment next_fleet_id. Day 3-5."""
        raise NotImplementedError("Phase 2 (apply actions) lands Day 3-5")

    def _phase_3_production(self, state: SimState) -> None:
        """env L514-517: planet.ships += planet.production for owner != -1."""
        for p in state.planets:
            if p.owner != -1:
                p.ships += p.production

    def _phase_4_advance_fleets(
        self, state: SimState, combat_lists: dict[int, list]
    ) -> None:
        """env L519-551: move fleets by speed; sun collision (< SUN_RADIUS, no margin);
        planet collision (< planet.radius, no margin); push hits into combat_lists. Day 5-7."""
        raise NotImplementedError("Phase 4 (advance fleets) lands Day 5-7")

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
