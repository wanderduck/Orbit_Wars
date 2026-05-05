"""Unit tests for validator.state_diff and ForwardModelValidator.validate."""
from __future__ import annotations

import pytest

from orbit_wars.sim.state import (
    SimConfig,
    SimFleet,
    SimPlanet,
    SimState,
)
from orbit_wars.sim.validator import state_diff


def _planet(id, owner=0, x=0.0, y=0.0, ships=10.0, production=1, radius=2.0, is_comet=False):
    return SimPlanet(
        id=id, owner=owner, x=x, y=y, radius=radius,
        ships=ships, production=production, is_comet=is_comet,
    )


def _state(planets, fleets=None, step=0):
    return SimState(
        step=step,
        planets=planets,
        fleets=fleets or [],
        comet_groups=[],
        angular_velocity=0.03,
        next_fleet_id=0,
        config=SimConfig(num_agents=2),
        initial_planets=list(planets),
    )


class TestStateDiff:
    def test_identical_states_no_diff(self):
        s1 = _state([_planet(0, owner=0, ships=10.0)])
        s2 = _state([_planet(0, owner=0, ships=10.0)])
        diff = state_diff(s1, s2, pos_tolerance=0.1, ship_tolerance=0)
        assert diff == {}

    def test_ownership_flip_detected(self):
        actual = _state([_planet(0, owner=0, ships=10.0)])
        expected = _state([_planet(0, owner=1, ships=10.0)])
        diff = state_diff(actual, expected)
        assert "ownership-flip" in diff
        assert diff["ownership-flip"] == 1  # one planet differs in owner

    def test_ship_count_off_detected(self):
        actual = _state([_planet(0, owner=0, ships=10.0)])
        expected = _state([_planet(0, owner=0, ships=12.0)])
        diff = state_diff(actual, expected, ship_tolerance=0)
        assert "ship-count-off" in diff

    def test_ship_count_within_tolerance_not_flagged(self):
        actual = _state([_planet(0, owner=0, ships=10.0)])
        expected = _state([_planet(0, owner=0, ships=10.5)])
        diff = state_diff(actual, expected, ship_tolerance=1)
        assert "ship-count-off" not in diff

    def test_step_mismatch_detected(self):
        actual = _state([_planet(0)], step=5)
        expected = _state([_planet(0)], step=6)
        diff = state_diff(actual, expected)
        assert "step-mismatch" in diff

    def test_fleet_count_mismatch_detected(self):
        f0 = SimFleet(id=0, owner=0, from_planet_id=0, target_planet_id=1,
                      x=5.0, y=5.0, angle=0.0, ships=3, spawned_at_step=0)
        actual = _state([_planet(0)], fleets=[])
        expected = _state([_planet(0)], fleets=[f0])
        diff = state_diff(actual, expected)
        assert "fleet-count-mismatch" in diff

    def test_fleet_position_drift_detected_above_tolerance(self):
        f0 = SimFleet(id=0, owner=0, from_planet_id=0, target_planet_id=1,
                      x=5.0, y=5.0, angle=0.0, ships=3, spawned_at_step=0)
        f1 = SimFleet(id=0, owner=0, from_planet_id=0, target_planet_id=1,
                      x=5.5, y=5.0, angle=0.0, ships=3, spawned_at_step=0)
        actual = _state([_planet(0)], fleets=[f0])
        expected = _state([_planet(0)], fleets=[f1])
        diff = state_diff(actual, expected, pos_tolerance=0.1)
        assert "fleet-position-drift" in diff

    def test_fleet_position_drift_within_tolerance_not_flagged(self):
        f0 = SimFleet(id=0, owner=0, from_planet_id=0, target_planet_id=1,
                      x=5.0, y=5.0, angle=0.0, ships=3, spawned_at_step=0)
        f1 = SimFleet(id=0, owner=0, from_planet_id=0, target_planet_id=1,
                      x=5.05, y=5.05, angle=0.0, ships=3, spawned_at_step=0)
        actual = _state([_planet(0)], fleets=[f0])
        expected = _state([_planet(0)], fleets=[f1])
        diff = state_diff(actual, expected, pos_tolerance=0.1)
        assert "fleet-position-drift" not in diff

    def test_multiple_categories_aggregated(self):
        actual = _state([_planet(0, owner=0, ships=10.0)], step=5)
        expected = _state([_planet(0, owner=1, ships=15.0)], step=6)
        diff = state_diff(actual, expected)
        assert set(diff.keys()) >= {"ownership-flip", "ship-count-off", "step-mismatch"}
