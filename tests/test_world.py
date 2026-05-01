"""Same-turn combat resolution and timeline simulation invariants.

Combat rules from E1 §Combat (and E3 §Methods):
1. Group arriving fleets by owner; sum same-owner ships.
2. Largest fights second-largest; difference survives.
3. Survivor: same owner as planet → reinforce; different → fight garrison.
4. Two-attacker tie → mutual annihilation (no survivor).
"""

from __future__ import annotations

import pytest

from orbit_wars.world import ArrivalEvent, WorldModel, resolve_arrival_event
from orbit_wars.state import ObservationView


class TestCombatResolution:
    def test_no_arrivals_keeps_state(self) -> None:
        owner, ships = resolve_arrival_event(owner=0, garrison=10.0, arrivals=[])
        assert owner == 0
        assert ships == 10.0

    def test_single_friendly_arrival_reinforces(self) -> None:
        owner, ships = resolve_arrival_event(
            owner=0,
            garrison=10.0,
            arrivals=[ArrivalEvent(eta=1, owner=0, ships=5)],
        )
        assert owner == 0
        assert ships == 15.0

    def test_single_enemy_arrival_below_garrison_keeps_owner(self) -> None:
        owner, ships = resolve_arrival_event(
            owner=0,
            garrison=10.0,
            arrivals=[ArrivalEvent(eta=1, owner=1, ships=5)],
        )
        assert owner == 0
        assert ships == 5.0

    def test_single_enemy_arrival_exceeds_garrison_flips_ownership(self) -> None:
        owner, ships = resolve_arrival_event(
            owner=0,
            garrison=5.0,
            arrivals=[ArrivalEvent(eta=1, owner=1, ships=10)],
        )
        assert owner == 1
        assert ships == 5.0  # surplus = 10 - 5

    def test_largest_minus_second_largest_survives(self) -> None:
        owner, ships = resolve_arrival_event(
            owner=0,
            garrison=2.0,
            arrivals=[
                ArrivalEvent(eta=1, owner=1, ships=15),
                ArrivalEvent(eta=1, owner=2, ships=5),
            ],
        )
        # owner1 has 10 surplus after fighting owner2, then fights garrison 2 -> flip with 8 ships
        assert owner == 1
        assert ships == 8.0

    def test_two_attacker_tie_annihilates_both(self) -> None:
        owner, ships = resolve_arrival_event(
            owner=0,
            garrison=10.0,
            arrivals=[
                ArrivalEvent(eta=1, owner=1, ships=15),
                ArrivalEvent(eta=1, owner=2, ships=15),
            ],
        )
        # Tied: all attackers destroyed, garrison untouched
        assert owner == 0
        assert ships == 10.0

    def test_same_owner_arrivals_aggregate(self) -> None:
        owner, ships = resolve_arrival_event(
            owner=0,
            garrison=5.0,
            arrivals=[
                ArrivalEvent(eta=1, owner=1, ships=8),
                ArrivalEvent(eta=1, owner=1, ships=2),  # same owner — aggregates
                ArrivalEvent(eta=1, owner=2, ships=3),
            ],
        )
        # owner 1 total = 10, owner 2 total = 3 → survivor (1, 7), then 7 vs 5 → flip, surplus 2
        assert owner == 1
        assert ships == 2.0


class TestTimeline:
    def test_neutral_planet_does_not_produce(self) -> None:
        from orbit_wars.world import _simulate_timeline
        owner_at, ships_at = _simulate_timeline(
            initial_owner=-1,
            initial_ships=10.0,
            initial_production=3,
            is_comet=False,
            arrivals=[],
            horizon=5,
        )
        assert owner_at == (-1, -1, -1, -1, -1, -1)
        assert ships_at == (10.0, 10.0, 10.0, 10.0, 10.0, 10.0)

    def test_owned_planet_produces_each_turn(self) -> None:
        from orbit_wars.world import _simulate_timeline
        owner_at, ships_at = _simulate_timeline(
            initial_owner=0,
            initial_ships=10.0,
            initial_production=3,
            is_comet=False,
            arrivals=[],
            horizon=5,
        )
        # Each turn: production (+3), then no combat → 10, 13, 16, 19, 22, 25
        assert ships_at == (10.0, 13.0, 16.0, 19.0, 22.0, 25.0)

    def test_arrival_overpowers_garrison_flips_ownership(self) -> None:
        from orbit_wars.world import _simulate_timeline
        owner_at, ships_at = _simulate_timeline(
            initial_owner=0,
            initial_ships=10.0,
            initial_production=2,
            is_comet=False,
            arrivals=[ArrivalEvent(eta=2, owner=1, ships=20)],
            horizon=5,
        )
        # turn 1: produce → 12 (owner 0)
        # turn 2: produce → 14, then combat: 20 vs 14 → flip to owner 1 with 6 ships
        # turn 3+: produce +2 each turn (production is a planet property, unaffected by capture)
        assert owner_at[2] == 1
        assert ships_at[2] == 6.0
        assert owner_at[3] == 1
        assert ships_at[3] == 8.0  # 6 + 2 production
        assert owner_at[4] == 1
        assert ships_at[4] == 10.0

    def test_comet_production_is_one(self) -> None:
        from orbit_wars.world import _simulate_timeline
        owner_at, ships_at = _simulate_timeline(
            initial_owner=0,
            initial_ships=5.0,
            initial_production=3,  # ignored for comets
            is_comet=True,
            arrivals=[],
            horizon=3,
        )
        # Comet production = 1 regardless of `initial_production`
        assert ships_at == (5.0, 6.0, 7.0, 8.0)


class TestWorldModelEndToEnd:
    @pytest.mark.slow
    def test_world_model_builds_from_real_env(self) -> None:
        """Smoke test: build a real env, advance one turn, build a WorldModel."""
        from kaggle_environments import make
        env = make("orbit_wars", debug=False)
        env.run(["random", "random"])
        # First post-launch step has actual planets
        first_obs = env.steps[1][0].observation
        view = ObservationView.from_raw(first_obs, step=1)
        assert len(view.planets) > 0, "expected populated initial planets"

        wm = WorldModel.from_observation(view)
        assert wm.horizon == 110
        # Every planet should have a timeline
        assert set(wm.base_timeline.keys()) == {p.id for p in view.planets}
        # Owned-planet ships should grow over time
        owned = view.my_planets
        if owned:
            timeline = wm.base_timeline[owned[0].id]
            # In the absence of attacks, owned planet's ships should be non-decreasing
            assert all(timeline.ships_at[i + 1] >= timeline.ships_at[i] for i in range(timeline.horizon))
