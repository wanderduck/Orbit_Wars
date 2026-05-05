"""Smoke tests for the orbit_wars.sim scaffold (Day 1 deliverable).

Exercises dataclass construction, action round-trips, validate_move's five
rejection paths, and confirms simulator stubs raise NotImplementedError.
The validator's collect_scenarios / validate methods land Day 1-2 / Day 3-5.
"""

from __future__ import annotations

import pytest

from orbit_wars.sim import (
    Action,
    ForwardModelValidator,
    SimConfig,
    SimFleet,
    SimPlanet,
    SimState,
    Simulator,
    validate_move,
)


def _state(planets: list[SimPlanet], fleets: list[SimFleet] | None = None) -> SimState:
    cfg = SimConfig()
    return SimState(
        step=0,
        planets=planets,
        fleets=fleets or [],
        comet_groups=[],
        angular_velocity=0.03,
        next_fleet_id=0,
        config=cfg,
        initial_planets=list(planets),
    )


class TestSimState:
    def test_planet_by_id_returns_match(self):
        p = SimPlanet(id=7, x=10, y=20, radius=2, owner=0, ships=10, production=1)
        assert _state([p]).planet_by_id(7) is p

    def test_planet_by_id_none_when_missing(self):
        assert _state([]).planet_by_id(99) is None

    def test_player_planets_filters_by_owner(self):
        p0 = SimPlanet(id=0, x=0, y=0, radius=2, owner=0, ships=5, production=1)
        p1 = SimPlanet(id=1, x=10, y=10, radius=2, owner=1, ships=8, production=1)
        pn = SimPlanet(id=2, x=20, y=20, radius=2, owner=-1, ships=3, production=1)
        state = _state([p0, p1, pn])
        assert state.player_planets(0) == [p0]
        assert state.player_planets(1) == [p1]
        assert state.player_planets(-1) == [pn]

    def test_alive_players_includes_planet_owners_and_fleet_owners(self):
        p0 = SimPlanet(id=0, x=0, y=0, radius=2, owner=0, ships=5, production=1)
        f1 = SimFleet(id=0, owner=1, from_planet_id=0, target_planet_id=0,
                      x=5, y=5, angle=0.0, ships=3, spawned_at_step=0)
        state = _state([p0], [f1])
        assert state.alive_players() == {0, 1}


class TestAction:
    def test_to_env_format_returns_three_element_list(self):
        a = Action(from_planet_id=3, angle=1.5, ships=20)
        assert a.to_env_format() == [3, 1.5, 20]

    def test_from_env_format_parses_correctly(self):
        a = Action.from_env_format([3, 1.5, 20])
        assert a.from_planet_id == 3
        assert a.angle == 1.5
        assert a.ships == 20

    def test_roundtrip_preserves_values(self):
        original = Action(from_planet_id=5, angle=2.71, ships=42)
        assert Action.from_env_format(original.to_env_format()) == original

    def test_from_env_format_rejects_wrong_shape(self):
        with pytest.raises(ValueError):
            Action.from_env_format([1, 2])
        with pytest.raises(ValueError):
            Action.from_env_format("not a list")  # type: ignore[arg-type]


class TestValidateMove:
    def _setup(self) -> SimState:
        return _state([
            SimPlanet(id=0, x=0, y=0, radius=2, owner=0, ships=10, production=1),
            SimPlanet(id=1, x=10, y=10, radius=2, owner=1, ships=8, production=1),
        ])

    def test_valid_move_passes(self):
        state = self._setup()
        assert validate_move(state, 0, Action(0, 0.5, 5)) is True

    def test_missing_source_rejected(self):
        state = self._setup()
        assert validate_move(state, 0, Action(99, 0.5, 5)) is False

    def test_unowned_source_rejected(self):
        state = self._setup()
        # planet 1 is owner=1; player 0 cannot launch from it
        assert validate_move(state, 0, Action(1, 0.5, 5)) is False

    def test_zero_or_negative_ships_rejected(self):
        state = self._setup()
        assert validate_move(state, 0, Action(0, 0.5, 0)) is False
        assert validate_move(state, 0, Action(0, 0.5, -1)) is False

    def test_insufficient_ships_rejected(self):
        state = self._setup()
        # planet 0 has 10 ships; request 11
        assert validate_move(state, 0, Action(0, 0.5, 11)) is False


class TestSimulatorStubs:
    def test_step_raises_until_phases_implemented(self):
        sim = Simulator()
        state = _state([SimPlanet(id=0, x=0, y=0, radius=2, owner=0, ships=10, production=1)])
        with pytest.raises(NotImplementedError):
            sim.step(state, {})


class TestValidatorStubs:
    def test_validate_raises_until_simulator_implemented(self):
        v = ForwardModelValidator(simulator=Simulator())
        with pytest.raises(NotImplementedError):
            v.validate([])


class TestExtractAndInject:
    """Round-trip extraction + injection on a real env episode (Day 1-2 deliverable).

    Exercises the verified extract/inject flow from the env-state-extraction agent.
    """

    def test_extract_returns_simstate_and_actions(self):
        from kaggle_environments import make
        from orbit_wars.sim.validator import extract_state_and_actions

        env = make("orbit_wars", debug=True, configuration={"seed": 7})
        env.run(["random", "random"])
        sim_state, actions = extract_state_and_actions(env, 5)
        assert sim_state.step == 5
        assert len(sim_state.planets) > 0
        assert len(actions) == 2  # 2 agents
        assert all(p in actions for p in (0, 1))

    def test_collect_scenarios_returns_triples(self):
        from orbit_wars.sim.validator import ForwardModelValidator

        v = ForwardModelValidator(simulator=Simulator())
        triples = v.collect_scenarios(seeds=[7], opponent_pool=["random"], max_steps_per_episode=10)
        assert len(triples) > 0
        # Each triple should have well-formed state_t and expected_state_t1
        for tri in triples:
            assert tri.state_t.step == tri.source_step
            assert tri.expected_state_t1.step == tri.source_step + 1
            assert tri.source_seed == 7

    def test_save_and_load_scenarios_roundtrips(self, tmp_path):
        from orbit_wars.sim.validator import ForwardModelValidator

        v = ForwardModelValidator(simulator=Simulator())
        triples = v.collect_scenarios(seeds=[7], opponent_pool=["random"], max_steps_per_episode=5)
        path = tmp_path / "triples.pkl"
        v.save_scenarios(triples, path)
        loaded = v.load_scenarios(path)
        assert len(loaded) == len(triples)
        assert loaded[0].source_seed == triples[0].source_seed
        assert loaded[0].source_step == triples[0].source_step

    @pytest.mark.slow
    def test_inject_step_matches_original_env(self):
        """End-to-end: extract → inject → step → result equals original env's next step.

        This is the Day-1 gate: prove the extraction + injection flow round-trips
        for at least non-comet-spawn-boundary transitions.
        """
        from kaggle_environments import make
        from orbit_wars.sim.validator import (
            extract_state_and_actions,
            inject_state_and_step,
        )

        env = make("orbit_wars", debug=True, configuration={"seed": 7})
        env.run(["random", "random"])
        # Sample non-spawn steps
        for src in [5, 30, 100, 200]:
            if src + 1 >= len(env.steps):
                continue
            state, actions = extract_state_and_actions(env, src)
            new_env = inject_state_and_step(state, actions)
            expected = env.steps[src + 1][0].observation
            actual = new_env.state[0].observation
            ep = {p[0]: list(p) for p in expected.planets}
            ap = {p[0]: list(p) for p in actual.planets}
            assert ep == ap, f"Mismatch at step {src}: planets diverged"
