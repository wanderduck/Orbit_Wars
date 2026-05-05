"""Per-phase property tests for the MCTS forward-model simulator."""
from __future__ import annotations

import pytest

from orbit_wars.sim.action import Action
from orbit_wars.sim.simulator import Simulator
from orbit_wars.sim.state import (
    SimConfig,
    SimFleet,
    SimPlanet,
    SimState,
)


def _planet(id, owner=0, x=0.0, y=0.0, ships=10.0, production=1, radius=2.0, is_comet=False):
    return SimPlanet(
        id=id, owner=owner, x=x, y=y, radius=radius,
        ships=ships, production=production, is_comet=is_comet,
    )


def _state(planets, fleets=None, step=0, next_fleet_id=0):
    return SimState(
        step=step,
        planets=planets,
        fleets=fleets or [],
        comet_groups=[],
        angular_velocity=0.03,
        next_fleet_id=next_fleet_id,
        config=SimConfig(num_agents=2),
        initial_planets=list(planets),
    )


class TestPhase3Production:
    def test_owned_planet_gains_production(self):
        sim = Simulator()
        state = _state([_planet(0, owner=0, ships=10.0, production=2)])
        sim._phase_3_production(state)
        assert state.planets[0].ships == 12.0

    def test_neutral_planet_unchanged(self):
        sim = Simulator()
        state = _state([_planet(0, owner=-1, ships=10.0, production=2)])
        sim._phase_3_production(state)
        assert state.planets[0].ships == 10.0

    def test_zero_production_unchanged(self):
        sim = Simulator()
        state = _state([_planet(0, owner=0, ships=10.0, production=0)])
        sim._phase_3_production(state)
        assert state.planets[0].ships == 10.0

    def test_multiple_owned_planets_all_produce(self):
        sim = Simulator()
        state = _state([
            _planet(0, owner=0, ships=10.0, production=2),
            _planet(1, owner=1, ships=5.0, production=3),
            _planet(2, owner=-1, ships=20.0, production=1),
        ])
        sim._phase_3_production(state)
        assert state.planets[0].ships == 12.0
        assert state.planets[1].ships == 8.0
        assert state.planets[2].ships == 20.0  # neutral


from orbit_wars.world import ArrivalEvent


class TestPhase6Combat:
    def test_no_arrivals_state_unchanged(self):
        sim = Simulator()
        state = _state([_planet(0, owner=0, ships=10.0)])
        combat_lists = {0: []}
        sim._phase_6_resolve_combat(state, combat_lists)
        assert state.planets[0].ships == 10.0
        assert state.planets[0].owner == 0

    def test_two_equal_arrivals_cancel_planet_undamaged(self):
        sim = Simulator()
        state = _state([_planet(0, owner=0, ships=10.0)])
        combat_lists = {0: [
            ArrivalEvent(eta=1, owner=1, ships=5),
            ArrivalEvent(eta=1, owner=2, ships=5),
        ]}
        sim._phase_6_resolve_combat(state, combat_lists)
        # Top-2 tie: mutual annihilation, garrison untouched, owner unchanged
        assert state.planets[0].ships == 10.0
        assert state.planets[0].owner == 0

    def test_top_one_beats_top_two_then_fights_garrison(self):
        sim = Simulator()
        state = _state([_planet(0, owner=0, ships=3.0)])  # garrison=3
        combat_lists = {0: [
            ArrivalEvent(eta=1, owner=1, ships=10),
            ArrivalEvent(eta=1, owner=2, ships=4),
        ]}
        sim._phase_6_resolve_combat(state, combat_lists)
        # Top-1 (owner=1, 10) - Top-2 (owner=2, 4) = 6 survives. 6 > garrison 3, capture.
        assert state.planets[0].owner == 1
        assert state.planets[0].ships == 3.0  # 6 - 3 = 3 remaining

    def test_same_owner_arrivals_merge_before_top_two_sort(self):
        sim = Simulator()
        state = _state([_planet(0, owner=-1, ships=0.0)])  # neutral, 0 ships
        combat_lists = {0: [
            ArrivalEvent(eta=1, owner=1, ships=4),
            ArrivalEvent(eta=1, owner=1, ships=4),  # same owner — merge to 8
            ArrivalEvent(eta=1, owner=2, ships=5),
        ]}
        sim._phase_6_resolve_combat(state, combat_lists)
        # Owner-1 totals 8; Owner-2 totals 5. Survivor: owner=1, 3 ships. Beats 0 garrison.
        assert state.planets[0].owner == 1
        assert state.planets[0].ships == 3.0

    def test_friendly_arrival_reinforces_garrison(self):
        sim = Simulator()
        state = _state([_planet(0, owner=0, ships=5.0)])
        combat_lists = {0: [ArrivalEvent(eta=1, owner=0, ships=7)]}
        sim._phase_6_resolve_combat(state, combat_lists)
        assert state.planets[0].owner == 0
        assert state.planets[0].ships == 12.0

    def test_single_arrival_loses_to_garrison(self):
        sim = Simulator()
        state = _state([_planet(0, owner=0, ships=10.0)])
        combat_lists = {0: [ArrivalEvent(eta=1, owner=1, ships=4)]}
        sim._phase_6_resolve_combat(state, combat_lists)
        # 4 attackers vs 10 garrison → garrison wins, reduced by 4
        assert state.planets[0].owner == 0
        assert state.planets[0].ships == 6.0


class TestPhase2ApplyActions:
    def test_accepted_launch_spawns_fleet(self):
        sim = Simulator()
        state = _state([
            _planet(0, owner=0, ships=10.0, x=20.0, y=30.0),
        ], next_fleet_id=42)
        actions = {0: [Action(from_planet_id=0, angle=1.5, ships=4)]}
        sim._phase_2_apply_actions(state, actions)
        assert len(state.fleets) == 1
        f = state.fleets[0]
        assert f.id == 42
        assert f.owner == 0
        assert f.from_planet_id == 0
        assert f.x == 20.0  # source planet position
        assert f.y == 30.0
        assert f.angle == 1.5
        assert f.ships == 4
        assert state.next_fleet_id == 43

    def test_accepted_launch_decrements_source_ships(self):
        sim = Simulator()
        state = _state([_planet(0, owner=0, ships=10.0)])
        actions = {0: [Action(from_planet_id=0, angle=0.0, ships=4)]}
        sim._phase_2_apply_actions(state, actions)
        assert state.planets[0].ships == 6.0

    def test_invalid_action_silently_dropped(self):
        sim = Simulator()
        state = _state([
            _planet(0, owner=0, ships=10.0),
            _planet(1, owner=1, ships=10.0),
        ], next_fleet_id=0)
        # Player 0 tries to launch from player 1's planet — silently rejected
        actions = {0: [Action(from_planet_id=1, angle=0.0, ships=5)]}
        sim._phase_2_apply_actions(state, actions)
        assert state.fleets == []
        assert state.next_fleet_id == 0
        assert state.planets[1].ships == 10.0  # unchanged

    def test_multiple_actions_per_player_assign_sequential_ids(self):
        sim = Simulator()
        state = _state([
            _planet(0, owner=0, ships=20.0),
        ], next_fleet_id=100)
        actions = {0: [
            Action(from_planet_id=0, angle=0.0, ships=3),
            Action(from_planet_id=0, angle=1.0, ships=4),
        ]}
        sim._phase_2_apply_actions(state, actions)
        assert len(state.fleets) == 2
        assert state.fleets[0].id == 100
        assert state.fleets[1].id == 101
        assert state.next_fleet_id == 102
        assert state.planets[0].ships == 13.0  # 20 - 3 - 4

    def test_actions_processed_in_player_order(self):
        sim = Simulator()
        state = _state([
            _planet(0, owner=0, ships=20.0),
            _planet(1, owner=1, ships=20.0),
        ], next_fleet_id=0)
        actions = {
            1: [Action(from_planet_id=1, angle=0.0, ships=3)],
            0: [Action(from_planet_id=0, angle=0.0, ships=3)],
        }
        sim._phase_2_apply_actions(state, actions)
        # Both spawned, player 0 first by ID
        assert len(state.fleets) == 2
        owners = [f.owner for f in state.fleets]
        assert owners == [0, 1]


class TestPhase0CometExpirationNoop:
    def test_no_comets_no_change(self):
        sim = Simulator()
        state = _state([_planet(0)])
        sim._phase_0_comet_expiration(state)
        # Day 3-5 scenarios have no comets; phase 0 is a no-op for now.
        assert state.comet_groups == []
        assert len(state.planets) == 1


class TestPhase4StubArrivalDetection:
    def test_in_flight_fleet_arriving_this_turn_pushed_to_combat_list(self):
        sim = Simulator()
        # Source at (0,0), target at (5,0). Fleet of 1 ship → speed = 1 (per fleet_speed formula).
        # Distance = 5; eta from current position would be ceil(5/1) = 5 turns.
        # Place the fleet at (4,0) so eta = ceil(1/1) = 1 turn.
        state = _state(
            [
                _planet(0, owner=0, ships=1.0, x=0.0, y=0.0, radius=2.0),
                _planet(1, owner=-1, ships=0.0, x=5.0, y=0.0, radius=2.0),
            ],
            fleets=[SimFleet(
                id=0, owner=0, from_planet_id=0, target_planet_id=1,
                x=4.0, y=0.0, angle=0.0, ships=1, spawned_at_step=0,
            )],
        )
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_4_advance_fleets(state, combat_lists)
        # Fleet should be flagged as arriving at planet 1 this turn
        assert len(combat_lists[1]) == 1
        assert combat_lists[1][0].owner == 0
        assert combat_lists[1][0].ships == 1
        # Fleet should be removed from the in-flight list (it arrived)
        assert state.fleets == []

    def test_in_flight_fleet_not_arriving_unchanged(self):
        sim = Simulator()
        state = _state(
            [
                _planet(0, owner=0, ships=10.0, x=0.0, y=0.0),
                _planet(1, owner=-1, ships=0.0, x=50.0, y=0.0),
            ],
            fleets=[SimFleet(
                id=0, owner=0, from_planet_id=0, target_planet_id=1,
                x=5.0, y=0.0, angle=0.0, ships=10, spawned_at_step=0,
            )],
        )
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_4_advance_fleets(state, combat_lists)
        # Far from target → not arriving this turn
        assert combat_lists[0] == []
        assert combat_lists[1] == []
        # Fleet is still in flight (not removed). Day 3-5 stub does NOT
        # advance the fleet's position; that lands Day 5-7.
        assert len(state.fleets) == 1

    def test_fleet_with_no_target_left_in_flight(self):
        """Fleets spawned in Phase 2 have target_planet_id=-1; stub leaves them in flight."""
        sim = Simulator()
        state = _state(
            [_planet(0, owner=0, ships=10.0, x=0.0, y=0.0)],
            fleets=[SimFleet(
                id=0, owner=0, from_planet_id=0, target_planet_id=-1,
                x=0.0, y=0.0, angle=0.5, ships=3, spawned_at_step=0,
            )],
        )
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_4_advance_fleets(state, combat_lists)
        # No target_planet_id resolved → stub cannot compute ETA, leaves it in flight
        assert len(state.fleets) == 1
        assert combat_lists[0] == []
