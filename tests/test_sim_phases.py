"""Per-phase property tests for the MCTS forward-model simulator."""
from __future__ import annotations

import math

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
        # Env spawns just outside the planet (planet.radius + 0.1 launch
        # clearance) so the fleet doesn't immediately collide with its origin.
        # See env L498-499. Default planet radius in _planet() is 2.0.
        clearance = 2.0 + 0.1
        assert f.x == pytest.approx(20.0 + math.cos(1.5) * clearance)
        assert f.y == pytest.approx(30.0 + math.sin(1.5) * clearance)
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


class TestPhase4FleetMovement:
    """Real Phase 4 (Day 5-7): fleet position update + sun + planet + OOB collision.

    Per env L519-551. Real Phase 4 doesn't use target_planet_id — collisions
    are checked against ALL planets on the path.
    """

    def test_fleet_arriving_pushed_to_combat_list_and_removed(self):
        sim = Simulator()
        # Fleet at (4,0), 1 ship → speed = 1.0. Planet 1 at (5,0) radius 2.
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
        # Path (4,0)→(5,0) hits planet 1 at (5,0).
        assert len(combat_lists[1]) == 1
        assert combat_lists[1][0].owner == 0
        assert combat_lists[1][0].ships == 1
        assert state.fleets == []

    def test_fleet_not_arriving_position_updated(self):
        sim = Simulator()
        # Fleet at (5,0), 10 ships → speed ≈ 1.96. Planets far away.
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
        assert combat_lists[0] == []
        assert combat_lists[1] == []
        assert len(state.fleets) == 1
        # Real Phase 4 advances position: speed for 10 ships ≈ 1.96
        expected_speed = 1.0 + 5.0 * (math.log(10) / math.log(1000)) ** 1.5
        assert state.fleets[0].x == pytest.approx(5.0 + expected_speed)
        assert state.fleets[0].y == pytest.approx(0.0)

    def test_fleet_oob_removed(self):
        """Fleet near board edge that walks past BOARD_SIZE=100 is removed."""
        sim = Simulator()
        state = _state(
            [_planet(0, owner=0, ships=10.0, x=0.0, y=50.0)],
            fleets=[SimFleet(
                id=0, owner=0, from_planet_id=0, target_planet_id=-1,
                x=99.5, y=50.0, angle=0.0, ships=1, spawned_at_step=0,
            )],
        )
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_4_advance_fleets(state, combat_lists)
        # Fleet walks to x=100.5 → OOB → removed; no combat
        assert state.fleets == []
        assert combat_lists[0] == []

    def test_fleet_sun_collision_removed(self):
        """Fleet aimed through the sun (segment crosses SUN_RADIUS=10) is destroyed."""
        sim = Simulator()
        # Fleet at (40, 50) heading toward sun center (50, 50). Speed ≥ 10
        # so segment crosses the sun. Use 1000 ships → speed = MAX_SPEED = 6.
        # 6 ships speed, segment from (40,50) to (46,50). Distance from
        # (50,50) to that segment = (50-46) = 4 < SUN_RADIUS=10. Collide.
        state = _state(
            [_planet(0, owner=0, ships=10.0, x=0.0, y=0.0)],
            fleets=[SimFleet(
                id=0, owner=0, from_planet_id=0, target_planet_id=-1,
                x=40.0, y=50.0, angle=0.0, ships=1000, spawned_at_step=0,
            )],
        )
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_4_advance_fleets(state, combat_lists)
        assert state.fleets == []
        assert combat_lists[0] == []

    def test_fleet_first_planet_on_path_wins(self):
        """When a fleet's path crosses two planets, env breaks on the FIRST
        match in iteration order (env L549). Mirror that determinism."""
        sim = Simulator()
        # Fleet at (0, 50) moving right at speed 6 (1000 ships).
        # Both planet A at (3, 50) radius 2 and planet B at (5, 50) radius 2
        # would intersect the segment (0,50)→(6,50). env iterates planets in
        # list order → planet A wins.
        state = _state(
            [
                _planet(0, owner=0, ships=10.0, x=80.0, y=80.0),  # source, far
                _planet(1, owner=-1, ships=0.0, x=3.0, y=50.0, radius=2.0),
                _planet(2, owner=-1, ships=0.0, x=5.0, y=50.0, radius=2.0),
            ],
            fleets=[SimFleet(
                id=0, owner=0, from_planet_id=0, target_planet_id=2,
                x=0.0, y=50.0, angle=0.0, ships=1000, spawned_at_step=0,
            )],
        )
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_4_advance_fleets(state, combat_lists)
        # Planet 1 (id=1) wins, planet 2 (id=2) gets nothing.
        assert len(combat_lists[1]) == 1
        assert combat_lists[2] == []
        assert state.fleets == []

    def test_fleet_just_spawned_does_not_self_collide(self):
        """A fleet spawned at planet.edge (Phase 2) walking outward does not
        hit its own source planet (the LAUNCH_CLEARANCE=0.1 buffer is enough)."""
        sim = Simulator()
        # Source planet at (10, 50) radius 2 — well clear of sun at (50,50).
        # Spawn at (12.1, 50) — just outside source. 1 ship → speed 1.
        # Walks to (13.1, 50).
        state = _state(
            [_planet(0, owner=0, ships=10.0, x=10.0, y=50.0, radius=2.0)],
            fleets=[SimFleet(
                id=0, owner=0, from_planet_id=0, target_planet_id=-1,
                x=12.1, y=50.0, angle=0.0, ships=1, spawned_at_step=0,
            )],
        )
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_4_advance_fleets(state, combat_lists)
        # Source at (10,50), segment (12.1, 50)→(13.1, 50), closest distance
        # from (10,50) to segment is 2.1 > radius 2.0 → NO collision.
        # Sun at (50,50) is 36.9 away from segment → no sun collision.
        assert combat_lists[0] == []
        assert len(state.fleets) == 1
        assert state.fleets[0].x == pytest.approx(13.1)


class TestPhase5RotationAndSweep:
    """Real Phase 5 (Day 7-9): planet rotation + sweep_fleets per env L553-627."""

    def test_static_planet_does_not_rotate(self):
        """A planet with orbital_r + radius >= 50 stays put."""
        sim = Simulator()
        # Planet at (5,5): orbital_r = sqrt(45^2+45^2) ≈ 63.6; +radius 2 = 65.6 >= 50 → static
        state = _state(
            [_planet(0, owner=0, ships=10.0, x=5.0, y=5.0, radius=2.0)],
            step=10,
        )
        # Use non-zero ang_vel — should still not rotate
        state.angular_velocity = 0.5
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_5_rotate_planets(state, combat_lists)
        assert state.planets[0].x == 5.0
        assert state.planets[0].y == 5.0

    def test_rotating_planet_position_updates_per_formula(self):
        """Planet at (60,50) with ang_vel=pi/2 step=1 rotates 90° → (50,60)."""
        sim = Simulator()
        # initial (60,50) → dx=10, dy=0, r=10, initial_angle=0
        # current_angle = 0 + (pi/2)*1 = pi/2
        # new_pos = (50 + 10*cos(pi/2), 50 + 10*sin(pi/2)) = (50, 60)
        # r + radius = 10 + 2 = 12 < 50 → rotates
        state = _state(
            [_planet(0, owner=0, ships=10.0, x=60.0, y=50.0, radius=2.0)],
            step=1,
        )
        state.angular_velocity = math.pi / 2
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_5_rotate_planets(state, combat_lists)
        assert state.planets[0].x == pytest.approx(50.0, abs=1e-9)
        assert state.planets[0].y == pytest.approx(60.0, abs=1e-9)

    def test_rotation_uses_initial_planet_for_radius_and_angle(self):
        """Rotation math uses initial_planets, not current. Verify via 2-step rotation."""
        sim = Simulator()
        # Initial (60,50). After step=2 with ang_vel=pi/2: angle = 0 + 2*pi/2 = pi
        # new_pos = (50 + 10*cos(pi), 50 + 10*sin(pi)) = (40, 50)
        # NOTE: current state.planets[0] position should not affect this.
        state = _state(
            [_planet(0, owner=0, ships=10.0, x=999.0, y=999.0, radius=2.0)],  # bogus current pos
            step=2,
        )
        state.angular_velocity = math.pi / 2
        # Override initial_planets to be at (60, 50)
        state.initial_planets = [_planet(0, x=60.0, y=50.0, radius=2.0)]
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_5_rotate_planets(state, combat_lists)
        assert state.planets[0].x == pytest.approx(40.0, abs=1e-9)
        assert state.planets[0].y == pytest.approx(50.0, abs=1e-9)

    def test_sweep_catches_fleet_in_swept_arc(self):
        """A rotating planet sweeps through a fleet's position → fleet consumed."""
        sim = Simulator()
        # Same setup as test 2: planet rotates from (60,50) to (50,60).
        # Fleet at midpoint (55, 55) — distance 0 from segment → swept.
        state = _state(
            [_planet(0, owner=-1, ships=0.0, x=60.0, y=50.0, radius=2.0)],
            fleets=[SimFleet(
                id=99, owner=1, from_planet_id=0, target_planet_id=0,
                x=55.0, y=55.0, angle=0.0, ships=5, spawned_at_step=0,
            )],
            step=1,
        )
        state.angular_velocity = math.pi / 2
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_5_rotate_planets(state, combat_lists)
        # Fleet swept → in combat_lists[0], removed from state.fleets
        assert len(combat_lists[0]) == 1
        assert combat_lists[0][0].owner == 1
        assert combat_lists[0][0].ships == 5
        assert state.fleets == []

    def test_sweep_skipped_when_planet_does_not_move(self):
        """Static planet (or planet that hasn't rotated) doesn't sweep."""
        sim = Simulator()
        # Static planet at (5,5). Fleet at (5,5) (right at planet position).
        # Even though fleet is colocated, static planet doesn't sweep.
        state = _state(
            [_planet(0, owner=-1, ships=0.0, x=5.0, y=5.0, radius=2.0)],
            fleets=[SimFleet(
                id=0, owner=1, from_planet_id=0, target_planet_id=0,
                x=5.0, y=5.0, angle=0.0, ships=5, spawned_at_step=0,
            )],
            step=10,
        )
        state.angular_velocity = 0.5
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_5_rotate_planets(state, combat_lists)
        assert combat_lists[0] == []
        assert len(state.fleets) == 1

    def test_sweep_does_not_catch_fleet_outside_arc(self):
        """Fleet far from the swept arc is not affected."""
        sim = Simulator()
        # Planet rotates from (60,50) to (50,60). Fleet at (5,5) — far away.
        state = _state(
            [_planet(0, owner=-1, ships=0.0, x=60.0, y=50.0, radius=2.0)],
            fleets=[SimFleet(
                id=0, owner=1, from_planet_id=0, target_planet_id=0,
                x=5.0, y=5.0, angle=0.0, ships=5, spawned_at_step=0,
            )],
            step=1,
        )
        state.angular_velocity = math.pi / 2
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_5_rotate_planets(state, combat_lists)
        assert combat_lists[0] == []
        assert len(state.fleets) == 1

    def test_fleet_swept_by_one_planet_not_double_swept(self):
        """A fleet caught by planet A's sweep is NOT also caught by planet B's sweep."""
        sim = Simulator()
        # Two rotating planets that both sweep through (55, 55):
        # Planet 0: (60,50) → (50,60) — sweeps through (55,55)
        # Planet 1: (50,40) → (60,50) — also sweeps through (55,45)... close but different
        # For simplicity, place two planets whose arcs cross at (55,55).
        # Planet 0 initial (60,50), step=1, ang_vel=pi/2 → goes (60,50)→(50,60).
        # Planet 1 initial (40,50), step=1, ang_vel=pi/2 → dx=-10, initial_angle=pi.
        #   current_angle = pi + pi/2 = 3pi/2. new_pos = (50 + 10*cos(3pi/2), 50 + 10*sin(3pi/2))
        #   = (50, 40). So planet 1 goes (40,50)→(50,40).
        # Fleet at (55,55) — only swept by planet 0.
        # That tests "one fleet, one planet sweeps it" — which is the common case.
        # For TRUE double-sweep prevention test: place fleet so BOTH planets' segments
        # would catch it. (50, 50) is close to both segments.
        state = _state(
            [
                _planet(0, owner=-1, ships=0.0, x=60.0, y=50.0, radius=20.0),  # giant radius
                _planet(1, owner=-1, ships=0.0, x=40.0, y=50.0, radius=20.0),  # giant radius
            ],
            fleets=[SimFleet(
                id=0, owner=1, from_planet_id=0, target_planet_id=0,
                x=50.0, y=50.0, angle=0.0, ships=5, spawned_at_step=0,
            )],
            step=1,
        )
        state.angular_velocity = math.pi / 2
        # Both planets rotate; both sweep arcs come close to (50,50). With radius=20,
        # both would catch it. But fleet should only be added to FIRST sweeper.
        combat_lists: dict[int, list] = {p.id: [] for p in state.planets}
        sim._phase_5_rotate_planets(state, combat_lists)
        total_arrivals = len(combat_lists[0]) + len(combat_lists[1])
        assert total_arrivals == 1, "Fleet swept once total, not twice"
        # First planet in iteration order (planet 0) wins
        assert len(combat_lists[0]) == 1
        assert combat_lists[1] == []
        assert state.fleets == []


class TestSimulatorStepIntegration:
    def test_step_runs_end_to_end_on_static_2p_state(self):
        """End-to-end step() on a Day-3-5-shaped scenario (static planets, 2P, no comets).

        Static planet positions chosen so they pass the gate filter:
            (5,5) → orbital_r + radius ≈ 65.6 >= 50 ✓
            (95,95) → same ✓
        """
        sim = Simulator()
        state = _state([
            _planet(0, owner=0, ships=10.0, x=5.0, y=5.0),
            _planet(1, owner=1, ships=10.0, x=95.0, y=95.0),
        ])
        actions = {
            0: [Action(from_planet_id=0, angle=0.5, ships=3)],
            1: [],
        }
        new_state = sim.step(state, actions)
        # Step incremented
        assert new_state.step == state.step + 1
        # Phase order: Phase 2 (apply actions) → Phase 3 (production) → Phase 4 → Phase 6.
        # Player 0 launched 3 ships from planet 0 (10 → 7), then production +1 = 8.
        assert new_state.planets[0].ships == 8.0
        # Player 1 didn't act; production +1 → 11
        assert new_state.planets[1].ships == 11.0
        # New fleet exists. target_planet_id=-1 (Phase 2 doesn't derive target),
        # so Phase 4 stub leaves it in flight.
        assert len(new_state.fleets) == 1
        f = new_state.fleets[0]
        assert f.owner == 0
        assert f.ships == 3
