# Plan C — Day 3-5 Minimal Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `ForwardModelValidator.validate()` + `state_diff()` + Simulator phases 0 (no-op), 2 (apply actions spawn), 3 (production), 4 (interim stub), and 6 (combat) such that the validator reports ≥80% match rate on filtered static-planet 2P scenarios per the Day 3-5 gate in `mcts_forward_model_design.md` Section 4.

**Architecture:** Validator-and-tests-first. Land `state_diff()` and `validate()` first so every subsequent phase implementation has an automated gate. Implement phases in fragility order: Phase 3 (production, trivial — smoke for validator) → Phase 6 (combat, port `world.resolve_arrival_event`) → Phase 2 (apply actions spawn, uses existing `validate_move`) → Phase 4 stub (in-flight fleets advance via straight-line ETA, borrow from `world.py` for arrival prediction). Each phase has hand-written property tests (5-8 per phase) plus the validator's match-rate as the integration check. Phase 5 (rotation) is excluded — Day 3-5 filters to static planets only; Phase 5 lands Day 7-9.

**Tech Stack:** Python 3.13, pytest + hypothesis, kaggle_environments. Reuses `src/orbit_wars/world.py` (resolve_arrival_event, path_collision_predicted, _build_arrival_ledger).

**Companion spec:** `docs/research_documents/2026-05-05-mcts-path-a-c-kickoff.md` (Section 3); master `mcts_forward_model_design.md` (Sections 3-4).

---

## File structure

| File | Role | Change |
|---|---|---|
| `src/orbit_wars/sim/validator.py` | Validation harness | Implement `state_diff()` and `validate()` |
| `src/orbit_wars/sim/simulator.py` | Forward model | Implement phases 0/2/3/4-stub/6; leave 1, 5 as raise |
| `tests/test_sim_phases.py` | Per-phase property tests | Create |
| `tests/test_sim_validator.py` | Validator unit tests | Create |
| `tests/test_sim_integration.py` | End-to-end ≥80% gate | Create |

---

## Task 1: state_diff — categorized mismatch detection

**Files:**
- Modify: `src/orbit_wars/sim/validator.py`
- Test: `tests/test_sim_validator.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_sim_validator.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_sim_validator.py -v`
Expected: ImportError on `state_diff`.

- [ ] **Step 3: Implement `state_diff`**

Edit `src/orbit_wars/sim/validator.py`. Add to the `__all__` export list (line 42-48):

```python
__all__ = [
    "ForwardModelValidator",
    "ValidationReport",
    "ValidationTriple",
    "extract_state_and_actions",
    "inject_state_and_step",
    "state_diff",
]
```

Add the function near the bottom of the file, before `ForwardModelValidator`:

```python
def state_diff(
    actual: SimState,
    expected: SimState,
    *,
    pos_tolerance: float = 0.1,
    ship_tolerance: int = 0,
) -> dict[str, int]:
    """Categorize differences between two SimStates.

    Returns a dict mapping category-name → count-of-diffs-in-that-category.
    Empty dict when states match within tolerances.

    Categories:
      - "step-mismatch":          state.step differs (count: 0 or 1)
      - "planet-count-mismatch":  len(planets) differs
      - "ownership-flip":         per-planet owner differs (count: # planets)
      - "ship-count-off":         per-planet ships differs by > ship_tolerance
      - "fleet-count-mismatch":   len(fleets) differs
      - "fleet-position-drift":   per-fleet (x,y) differs by > pos_tolerance
                                  (only checked when fleet IDs match in both states)
      - "fleet-id-set-mismatch":  fleet ID set differs
      - "comet-related":          comet group count or path_index differs

    Each category counts AT MOST per-element (not summed across multiple
    fields of one element). For Day 3-5, "fleet-position-drift" is expected
    to be common because the simulator's Phase 4 stub doesn't move fleets.
    """
    diff: dict[str, int] = {}

    if actual.step != expected.step:
        diff["step-mismatch"] = 1

    # Planets
    if len(actual.planets) != len(expected.planets):
        diff["planet-count-mismatch"] = abs(len(actual.planets) - len(expected.planets))
    actual_p_by_id = {p.id: p for p in actual.planets}
    expected_p_by_id = {p.id: p for p in expected.planets}
    common_p_ids = set(actual_p_by_id) & set(expected_p_by_id)
    own_diffs = 0
    ship_diffs = 0
    for pid in common_p_ids:
        ap, ep = actual_p_by_id[pid], expected_p_by_id[pid]
        if ap.owner != ep.owner:
            own_diffs += 1
        if abs(ap.ships - ep.ships) > ship_tolerance:
            ship_diffs += 1
    if own_diffs:
        diff["ownership-flip"] = own_diffs
    if ship_diffs:
        diff["ship-count-off"] = ship_diffs

    # Fleets
    if len(actual.fleets) != len(expected.fleets):
        diff["fleet-count-mismatch"] = abs(len(actual.fleets) - len(expected.fleets))
    actual_f_by_id = {f.id: f for f in actual.fleets}
    expected_f_by_id = {f.id: f for f in expected.fleets}
    if set(actual_f_by_id) != set(expected_f_by_id):
        diff["fleet-id-set-mismatch"] = len(set(actual_f_by_id) ^ set(expected_f_by_id))
    common_f_ids = set(actual_f_by_id) & set(expected_f_by_id)
    pos_diffs = 0
    for fid in common_f_ids:
        af, ef = actual_f_by_id[fid], expected_f_by_id[fid]
        if abs(af.x - ef.x) > pos_tolerance or abs(af.y - ef.y) > pos_tolerance:
            pos_diffs += 1
    if pos_diffs:
        diff["fleet-position-drift"] = pos_diffs

    # Comets (basic — full coverage lands Day 9-11)
    if len(actual.comet_groups) != len(expected.comet_groups):
        diff["comet-related"] = abs(len(actual.comet_groups) - len(expected.comet_groups))

    return diff
```

- [ ] **Step 4: Run tests to verify all 9 pass**

Run: `uv run pytest tests/test_sim_validator.py::TestStateDiff -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/orbit_wars/sim/validator.py tests/test_sim_validator.py
git commit -m "$(cat <<'EOF'
feat(sim): add state_diff for categorized validator mismatches

Per kickoff brief Section 3.1: returns dict of category→count for the 7
expected mismatch categories (step, planet-count, ownership-flip,
ship-count-off, fleet-count, fleet-id-set, fleet-position-drift,
comet-related). Each category counted per-element (no summing). Empty
dict on full match. Drives the 'fix most-frequent category, re-run' loop.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: ForwardModelValidator.validate()

**Files:**
- Modify: `src/orbit_wars/sim/validator.py` (`validate` method)
- Test: `tests/test_sim_validator.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_sim_validator.py`:

```python
class _IdentitySimulator:
    """Stub simulator that returns the EXPECTED next state (always matches)."""

    def __init__(self, lookup: dict[tuple[int, int], "SimState"]):
        # lookup[(seed, step)] -> expected_state_t1
        self._lookup = lookup

    def step(self, state, actions):
        # Look up by (state.step, id(state)) — keep it simple, callers preload.
        return self._next_state


class TestForwardModelValidator:
    def test_validate_returns_match_rate_with_identity_sim(self):
        from orbit_wars.sim.simulator import Simulator
        from orbit_wars.sim.validator import (
            ForwardModelValidator,
            ValidationTriple,
        )

        s_t = _state([_planet(0, owner=0, ships=10.0)], step=5)
        s_t1 = _state([_planet(0, owner=0, ships=11.0)], step=6)  # production +1

        # IdentitySim that always returns s_t1 — guaranteed match.
        class IdentitySim:
            def step(self, state, actions):
                return s_t1

        triples = [
            ValidationTriple(
                state_t=s_t,
                actions_t={0: [], 1: []},
                expected_state_t1=s_t1,
                source_seed=0,
                source_step=5,
            )
        ]
        v = ForwardModelValidator(simulator=IdentitySim())
        report = v.validate(triples)
        assert report.n_total == 1
        assert report.n_match == 1
        assert report.match_rate == 1.0

    def test_validate_categorizes_mismatch_with_stub_sim(self):
        from orbit_wars.sim.validator import (
            ForwardModelValidator,
            ValidationTriple,
        )

        s_t = _state([_planet(0, owner=0, ships=10.0)], step=5)
        s_t1_real = _state([_planet(0, owner=1, ships=10.0)], step=6)  # ownership flip
        s_t1_pred = _state([_planet(0, owner=0, ships=10.0)], step=6)  # sim says no flip

        class WrongSim:
            def step(self, state, actions):
                return s_t1_pred

        triples = [
            ValidationTriple(
                state_t=s_t,
                actions_t={0: [], 1: []},
                expected_state_t1=s_t1_real,
                source_seed=0,
                source_step=5,
            )
        ]
        v = ForwardModelValidator(simulator=WrongSim())
        report = v.validate(triples)
        assert report.n_total == 1
        assert report.n_match == 0
        assert report.mismatch_categories.get("ownership-flip", 0) == 1

    def test_validate_skips_categories_when_gate_filter_applied(self):
        from orbit_wars.sim.validator import (
            ForwardModelValidator,
            ValidationTriple,
        )

        s_t = _state(
            [_planet(0, owner=0, ships=10.0)],
            fleets=[SimFleet(id=0, owner=0, from_planet_id=0, target_planet_id=1,
                             x=5.0, y=5.0, angle=0.0, ships=3, spawned_at_step=0)],
            step=5,
        )
        s_t1_real = _state(
            [_planet(0, owner=0, ships=11.0)],  # production
            fleets=[SimFleet(id=0, owner=0, from_planet_id=0, target_planet_id=1,
                             x=11.0, y=5.0, angle=0.0, ships=3, spawned_at_step=0)],
            step=6,
        )
        s_t1_pred = _state(
            [_planet(0, owner=0, ships=11.0)],  # production correct
            fleets=[SimFleet(id=0, owner=0, from_planet_id=0, target_planet_id=1,
                             x=5.0, y=5.0, angle=0.0, ships=3, spawned_at_step=0)],  # NOT moved
            step=6,
        )

        class StubSim:
            def step(self, state, actions):
                return s_t1_pred

        triples = [
            ValidationTriple(
                state_t=s_t,
                actions_t={0: [], 1: []},
                expected_state_t1=s_t1_real,
                source_seed=0,
                source_step=5,
            )
        ]
        # Default gate (all categories) → mismatch (fleet-position-drift)
        v = ForwardModelValidator(simulator=StubSim())
        report_default = v.validate(triples)
        assert report_default.n_match == 0

        # Day-3-5 gate (ignore fleet-position-drift) → match
        report_d35 = v.validate(triples, gate_categories={"ownership-flip", "ship-count-off", "step-mismatch", "planet-count-mismatch", "fleet-count-mismatch", "comet-related"})
        assert report_d35.n_match == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_sim_validator.py::TestForwardModelValidator -v`
Expected: NotImplementedError raised by current `validate` stub.

- [ ] **Step 3: Implement `validate()`**

Edit `src/orbit_wars/sim/validator.py`. Replace the existing `validate` method (~line 317-328) with:

```python
    def validate(
        self,
        triples: list[ValidationTriple],
        *,
        gate_categories: set[str] | None = None,
    ) -> ValidationReport:
        """Run Simulator.step on each triple; compare to expected.

        `gate_categories`, when provided, is the set of mismatch categories
        that count toward "did this triple match" — categories OUTSIDE this
        set are recorded in mismatch_categories aggregates but do NOT
        disqualify a triple. Default = all categories matter.

        Used for Day 3-5 to ignore "fleet-position-drift" (the Phase 4 stub
        doesn't move fleets) while still gating on planet-side correctness.
        """
        n_match = 0
        mismatches: list[tuple[ValidationTriple, dict]] = []
        category_totals: dict[str, int] = {}

        for tri in triples:
            actual = self.simulator.step(tri.state_t, tri.actions_t)
            diff = state_diff(
                actual,
                tri.expected_state_t1,
                pos_tolerance=self.pos_tolerance,
                ship_tolerance=self.ship_tolerance,
            )
            for cat, count in diff.items():
                category_totals[cat] = category_totals.get(cat, 0) + count

            if gate_categories is None:
                gating_diff = diff
            else:
                gating_diff = {k: v for k, v in diff.items() if k in gate_categories}

            if not gating_diff:
                n_match += 1
            else:
                mismatches.append((tri, diff))

        return ValidationReport(
            n_total=len(triples),
            n_match=n_match,
            mismatches=mismatches[:50],
            mismatch_categories=category_totals,
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_sim_validator.py -v`
Expected: 9 (state_diff) + 3 (validator) = 12 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/orbit_wars/sim/validator.py tests/test_sim_validator.py
git commit -m "$(cat <<'EOF'
feat(sim): implement ForwardModelValidator.validate with category gating

Walks triples calling simulator.step, aggregates state_diff results into
ValidationReport. Optional gate_categories filter lets Day 3-5 ignore
'fleet-position-drift' (Phase 4 stub doesn't move fleets) while still
gating on planet-side correctness. Day 14 will use the unfiltered gate.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Phase 3 — production

**Files:**
- Modify: `src/orbit_wars/sim/simulator.py` (`_phase_3_production`)
- Test: `tests/test_sim_phases.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_sim_phases.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_sim_phases.py::TestPhase3Production -v`
Expected: NotImplementedError raised by stub.

- [ ] **Step 3: Implement `_phase_3_production`**

Edit `src/orbit_wars/sim/simulator.py`. Replace `_phase_3_production` body (~line 93-95):

```python
    def _phase_3_production(self, state: SimState) -> None:
        """env L514-517: planet.ships += planet.production for owner != -1."""
        for p in state.planets:
            if p.owner != -1:
                p.ships += p.production
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_sim_phases.py::TestPhase3Production -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/orbit_wars/sim/simulator.py tests/test_sim_phases.py
git commit -m "$(cat <<'EOF'
feat(sim): implement Phase 3 (production)

Trivial port of env L514-517: owned planets gain production each turn.
First phase to land. Acts as smoke for the validator pipeline before
combat (Phase 6) and apply-actions (Phase 2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Phase 6 — combat resolution

Phase 6 drains `combat_lists` (a `dict[planet_id, list[ArrivalEvent]]` populated by Phase 4) and resolves combat per planet using `world.resolve_arrival_event`.

**Files:**
- Modify: `src/orbit_wars/sim/simulator.py`
- Test: `tests/test_sim_phases.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_sim_phases.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_sim_phases.py::TestPhase6Combat -v`
Expected: NotImplementedError.

- [ ] **Step 3: Implement `_phase_6_resolve_combat`**

Edit `src/orbit_wars/sim/simulator.py`. Replace the stub (~line 111-116):

```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_sim_phases.py::TestPhase6Combat -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/orbit_wars/sim/simulator.py tests/test_sim_phases.py
git commit -m "$(cat <<'EOF'
feat(sim): implement Phase 6 (combat resolution)

Per planet, drain arrivals from combat_lists and resolve via
world.resolve_arrival_event (faithful E1 §Combat port). Tests cover
top-2 tie cancel, top-1 strict win + garrison fight, same-owner merge,
friendly reinforcement, single attacker loses to garrison.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Phase 2 — apply actions (spawn half)

Phase 2 walks `actions[player_id]`, calls `validate_move`, and spawns accepted launches as new `SimFleet` entries with monotonic IDs.

**Files:**
- Modify: `src/orbit_wars/sim/simulator.py`
- Test: `tests/test_sim_phases.py`

The new fleet's initial position is the source planet's position (`from_planet.x`, `from_planet.y`); the angle comes from the action; the target_planet_id is left as `-1` for now (Phase 4 stub will derive it). `spawned_at_step = state.step` (after Phase 0/1 step increment in `step()`).

- [ ] **Step 1: Add tests**

Append to `tests/test_sim_phases.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_sim_phases.py::TestPhase2ApplyActions -v`
Expected: NotImplementedError.

- [ ] **Step 3: Implement `_phase_2_apply_actions`**

Edit `src/orbit_wars/sim/simulator.py`. Replace the stub (~line 87-91):

```python
    def _phase_2_apply_actions(
        self, state: SimState, actions: dict[int, list[Action]]
    ) -> None:
        """env L479-512: validate each move, spawn accepted fleets, increment next_fleet_id.

        Process players in ascending player_id order so fleet IDs are stable
        across runs (matches env behavior — env iterates players in fixed
        order per env L479).
        """
        from .action import validate_move

        for player_id in sorted(actions):
            for action in actions[player_id]:
                if not validate_move(state, player_id, action):
                    continue
                src = state.planet_by_id(action.from_planet_id)
                # validate_move guarantees src is non-None and player-owned
                assert src is not None
                fleet = SimFleet(
                    id=state.next_fleet_id,
                    owner=player_id,
                    from_planet_id=src.id,
                    target_planet_id=-1,        # derived later by Phase 4 if needed
                    x=src.x,
                    y=src.y,
                    angle=action.angle,
                    ships=action.ships,
                    spawned_at_step=state.step,
                )
                state.fleets.append(fleet)
                state.next_fleet_id += 1
                src.ships -= action.ships
```

Note: the `from .action import validate_move` line at the top of the file may need adding if not already present. Add at the top with other imports:

```python
from .action import Action, validate_move
```

(replacing the existing `from .action import Action`).

Also need: `from .state import SimFleet, SimState` (the existing `from .state import SimState` may need extending). Update the imports at top of simulator.py:

```python
from .action import Action, validate_move
from .state import SimFleet, SimState
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_sim_phases.py::TestPhase2ApplyActions -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/orbit_wars/sim/simulator.py tests/test_sim_phases.py
git commit -m "$(cat <<'EOF'
feat(sim): implement Phase 2 (apply actions, spawn half)

Walks actions per player (ascending ID, matches env L479 order). Calls
validate_move; on accept, spawns SimFleet with monotonic next_fleet_id
and decrements source planet ships. Invalid moves silently dropped per
env quirk #11.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Phase 0 + Phase 4 stub + Simulator.step() wire-up

Phase 0 (comet expiration) is a no-op for Day 3-5 since the scenario filter excludes comets. Phase 4 stub borrows `world._build_arrival_ledger` for ETA computation: when an in-flight fleet's ETA == 1 this turn, push it into combat_lists for its target. Day 3-5's filter ensures static planets only, so the world helper is safe (its known bug is for moving-planet sweeps).

**Files:**
- Modify: `src/orbit_wars/sim/simulator.py`
- Test: `tests/test_sim_phases.py`

- [ ] **Step 1: Add tests for Phase 0 and Phase 4 stub**

Append to `tests/test_sim_phases.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_sim_phases.py::TestPhase0CometExpirationNoop tests/test_sim_phases.py::TestPhase4StubArrivalDetection -v`
Expected: NotImplementedError.

- [ ] **Step 3: Implement Phase 0 (no-op) and Phase 4 stub**

Edit `src/orbit_wars/sim/simulator.py`. Replace `_phase_0_comet_expiration` (~line 75-77) with:

```python
    def _phase_0_comet_expiration(self, state: SimState) -> None:
        """env L419-439: drop comets where path_index >= len(path).

        Day 3-5 scenarios are filtered to exclude comets; this is a no-op
        for now. Real implementation lands Day 9-11.
        """
        # Intentional no-op for Day 3-5. Comet-bearing scenarios are filtered
        # out by the validator's scenario filter; if a comet appears here
        # despite the filter, the next-state validator diff will catch it
        # under "comet-related".
        return
```

Replace `_phase_4_advance_fleets` (~line 97-102) with:

```python
    def _phase_4_advance_fleets(
        self, state: SimState, combat_lists: dict[int, list]
    ) -> None:
        """env L519-551: STUB. Detect in-flight fleets arriving THIS turn
        and push them into combat_lists. Does NOT advance fleet positions.

        Day 3-5 stub: borrows fleet ETA prediction from world (safe for
        static planets only). Real Phase 4 (sun + planet collisions,
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
            distance = dist((fleet.x, fleet.y), (target.x, target.y))
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_sim_phases.py::TestPhase0CometExpirationNoop tests/test_sim_phases.py::TestPhase4StubArrivalDetection -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/orbit_wars/sim/simulator.py tests/test_sim_phases.py
git commit -m "$(cat <<'EOF'
feat(sim): Phase 0 no-op + Phase 4 interim stub for Day 3-5 gate

Phase 0 is a documented no-op (comets filtered by Day 3-5 scenario set).
Phase 4 stub detects in-flight fleets arriving THIS turn (via straight-
line ETA from current position; safe for static planets) and pushes
ArrivalEvent into combat_lists. Does NOT update fleet positions —
expected mismatch for the 'fleet-position-drift' category which Day 3-5
gate ignores. Real Phase 4 lands Day 5-7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: End-to-end Simulator.step() smoke test

Verify `step()` runs end-to-end without raising on a filtered scenario.

**Files:**
- Test: `tests/test_sim_phases.py`

- [ ] **Step 1: Add the integration smoke test**

Append to `tests/test_sim_phases.py`:

```python
class TestSimulatorStepIntegration:
    def test_step_runs_end_to_end_on_simple_state(self):
        sim = Simulator()
        state = _state([
            _planet(0, owner=0, ships=10.0, x=20.0, y=30.0),
            _planet(1, owner=1, ships=10.0, x=80.0, y=70.0),
        ])
        actions = {
            0: [Action(from_planet_id=0, angle=0.5, ships=3)],
            1: [],
        }
        new_state = sim.step(state, actions)
        # Step incremented
        assert new_state.step == state.step + 1
        # Production happened (owned planets gained 1)
        # Phase 2 spawned a fleet for player 0; that fleet has ships=3 so
        # source planet went 10 - 3 = 7, then production +1 = 8
        # Wait — phase order is: Phase 2 (apply actions), Phase 3 (production),
        # Phase 4 (advance), Phase 5 (skip), Phase 6 (resolve).
        # So source planet: 10 - 3 (action) + 1 (production) = 8
        assert new_state.planets[0].ships == 8.0
        # Player 1 didn't act; production +1 → 11
        assert new_state.planets[1].ships == 11.0
        # New fleet exists (won't have arrived: target=-1, Phase 4 stub
        # leaves it in flight)
        assert len(new_state.fleets) == 1
        f = new_state.fleets[0]
        assert f.owner == 0
        assert f.ships == 3
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_sim_phases.py::TestSimulatorStepIntegration -v`
Expected: 1 passed.

- [ ] **Step 3: Run the FULL phase test suite as a sanity check**

Run: `uv run pytest tests/test_sim_phases.py tests/test_sim_validator.py tests/test_sim.py -v`
Expected: all passed (test_sim.py's `test_step_raises_until_phases_implemented` will FAIL because step no longer raises — that's expected; we'll fix it in this same task).

- [ ] **Step 4: Update the obsolete test in tests/test_sim.py**

Find `TestSimulatorStubs.test_step_raises_until_phases_implemented` in `tests/test_sim.py` (~line 116-121) and replace with:

```python
class TestSimulatorPhaseStubs:
    def test_phase_1_comet_spawn_still_raises(self):
        """Phase 1 (comet spawn) intentionally raises NotImplementedError —
        the env's RNG can't be reproduced; spawn is handled outside the sim."""
        sim = Simulator()
        state = _state([SimPlanet(id=0, x=0, y=0, radius=2, owner=0, ships=10, production=1)])
        with pytest.raises(NotImplementedError):
            sim._phase_1_comet_spawn(state)

    def test_phase_5_rotation_still_raises(self):
        """Phase 5 (rotation + sweep) lands Day 7-9; should still raise."""
        sim = Simulator()
        state = _state([SimPlanet(id=0, x=0, y=0, radius=2, owner=0, ships=10, production=1)])
        with pytest.raises(NotImplementedError):
            sim._phase_5_rotate_planets(state, {})
```

Also update `TestValidatorStubs.test_validate_raises_until_simulator_implemented` — `validate()` no longer raises. Replace with:

```python
class TestValidatorBasic:
    def test_validate_returns_empty_report_on_no_triples(self):
        v = ForwardModelValidator(simulator=Simulator())
        report = v.validate([])
        assert report.n_total == 0
        assert report.n_match == 0
        assert report.match_rate == 0.0
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/test_sim*.py -v`
Expected: all pass; no NotImplementedError except the two phase stubs we explicitly test for.

- [ ] **Step 6: Commit**

```bash
git status -s
git add src/orbit_wars/sim/simulator.py tests/test_sim_phases.py tests/test_sim.py
git commit -m "$(cat <<'EOF'
feat(sim): wire up Simulator.step() integration; update obsolete stubs tests

step() now runs end-to-end on filtered Day-3-5 scenarios (phases 0/2/3/4-stub/6
implemented; 1 and 5 still raise NotImplementedError as expected).
Updated tests/test_sim.py to reflect new state: phase-1 (comet spawn) and
phase-5 (rotation) still raise; validate() now returns empty report on
empty triple list rather than raising.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: The 80% match-rate gate — end-to-end validation

The Day 3-5 gate. Collect filtered scenarios, run validator with the gate-categories filter, report match rate. Lands as a slow-marked integration test plus a CLI smoke command.

**Files:**
- Test: `tests/test_sim_integration.py` (create)
- Modify: `src/orbit_wars/sim/validator.py` (add a scenario filter helper)

- [ ] **Step 1: Add a scenario filter helper to validator.py**

Edit `src/orbit_wars/sim/validator.py`. Add to `__all__`:

```python
__all__ = [
    "ForwardModelValidator",
    "ValidationReport",
    "ValidationTriple",
    "extract_state_and_actions",
    "filter_day_3_5_scenarios",
    "inject_state_and_step",
    "state_diff",
]
```

Add the function near the top of the file, after the COMET_SPAWN_STEPS constant:

```python
# Per env L572: planets with orbital_r + radius >= ROTATION_RADIUS_LIMIT
# are not rotated. This is the same condition used to identify "static"
# planets for Day 3-5 scenario filtering.
ROTATION_RADIUS_LIMIT = 50.0  # env constant
SUN_CENTER = (50.0, 50.0)


def _orbital_radius(planet) -> float:
    """Distance from sun (env's pivot for rotation)."""
    import math
    return math.hypot(planet.x - SUN_CENTER[0], planet.y - SUN_CENTER[1])


def filter_day_3_5_scenarios(
    triples: list[ValidationTriple],
) -> list[ValidationTriple]:
    """Filter triples to the Day 3-5 gate set per kickoff brief Section 3.3.

    Keeps only triples where ALL hold:
      - state_t has no comet groups present
      - all planets in state_t are STATIC (orbital_r + radius >= 50)
      - state_t.step is NOT in COMET_SPAWN_STEPS
      - state_t.step + 1 is NOT in COMET_SPAWN_STEPS
      - 2P games only (state_t.config.num_agents == 2)
    """
    out: list[ValidationTriple] = []
    for tri in triples:
        s = tri.state_t
        if s.comet_groups:
            continue
        if s.config.num_agents != 2:
            continue
        if s.step in COMET_SPAWN_STEPS:
            continue
        if (s.step + 1) in COMET_SPAWN_STEPS:
            continue
        # All planets must be static
        all_static = all(
            _orbital_radius(p) + p.radius >= ROTATION_RADIUS_LIMIT
            for p in s.planets
        )
        if not all_static:
            continue
        out.append(tri)
    return out
```

- [ ] **Step 2: Add the gate test**

Create `tests/test_sim_integration.py`:

```python
"""End-to-end Day 3-5 gate: ≥80% match rate on filtered static-2P scenarios."""
from __future__ import annotations

import pytest


GATE_CATEGORIES = {
    "ownership-flip",
    "ship-count-off",
    "step-mismatch",
    "planet-count-mismatch",
    "fleet-count-mismatch",
    "comet-related",
}
# NOT in gate: "fleet-position-drift", "fleet-id-set-mismatch" — Phase 4 stub
# doesn't move fleets; mismatches there are expected and resolve Day 5-7.


@pytest.mark.slow
def test_day_3_5_gate_match_rate_at_least_80_percent():
    """Day 3-5 gate per kickoff brief Section 3.4 + master design doc Section 4."""
    from orbit_wars.sim.simulator import Simulator
    from orbit_wars.sim.validator import (
        ForwardModelValidator,
        filter_day_3_5_scenarios,
    )

    seeds = list(range(10))
    opponent_pool = ["random", "starter"]
    opponent_combos = [
        (opp_a, opp_b)
        for opp_a in opponent_pool
        for opp_b in opponent_pool
    ]

    v = ForwardModelValidator(simulator=Simulator())
    raw_triples = v.collect_scenarios(
        seeds=seeds,
        opponent_pool=opponent_pool,
        opponent_combos=opponent_combos,
    )
    filtered = filter_day_3_5_scenarios(raw_triples)
    assert len(filtered) >= 200, (
        f"Day 3-5 filter too aggressive: only {len(filtered)} triples from "
        f"{len(raw_triples)} raw. Expand seeds or opponent pool."
    )

    report = v.validate(filtered, gate_categories=GATE_CATEGORIES)
    print(f"\nDay 3-5 gate: n_total={report.n_total}  n_match={report.n_match}  "
          f"match_rate={report.match_rate:.3f}")
    print(f"Mismatch categories: {report.mismatch_categories}")

    assert report.match_rate >= 0.80, (
        f"Day 3-5 gate FAILED: match_rate={report.match_rate:.3f} < 0.80. "
        f"Top mismatch categories: {sorted(report.mismatch_categories.items(), key=lambda kv: -kv[1])[:5]}"
    )
```

- [ ] **Step 3: Run the gate test**

Run: `uv run pytest tests/test_sim_integration.py -v -s -m slow`
Expected: passes with `match_rate >= 0.80`. The test prints the actual match rate and category breakdown for diagnostics.

If FAIL: read the printed mismatch categories. Most-frequent category indicates which phase has bugs. Fix the phase, re-run. Per design doc, hard kill of C only at Day 14; here we have a single debug day before re-deciding per kickoff brief Section 4.

- [ ] **Step 4: Commit**

```bash
git status -s
git add src/orbit_wars/sim/validator.py tests/test_sim_integration.py
git commit -m "$(cat <<'EOF'
feat(sim): Day 3-5 gate test — >=80% match rate on static-2P scenarios

Adds filter_day_3_5_scenarios helper (excludes comets, dynamic planets,
spawn-boundary turns, 4P games) and an integration test that asserts
match_rate >= 0.80 with fleet-position-drift excluded from the gate
(expected mismatch — Phase 4 stub doesn't move fleets).

Closes Day 3-5 of the master MCTS forward-model design doc Section 4.
Per kickoff brief 2026-05-05 Section 3.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Document the gate result + decide next move

**Files:**
- Create: `docs/iteration_logs/2026-05-05-sim-day-3-5-gate.md`

- [ ] **Step 1: Run the gate test once more and capture output**

```bash
uv run pytest tests/test_sim_integration.py -v -s -m slow 2>&1 | tee /tmp/gate-output.txt
```

- [ ] **Step 2: Write the iteration log**

Create `docs/iteration_logs/2026-05-05-sim-day-3-5-gate.md`:

```markdown
# Day 3-5 simulator gate result — 2026-05-05

**Plan:** `docs/research_documents/2026-05-05-plan-c-day-3-5-minimal-sim.md`
**Master design:** `docs/research_documents/mcts_forward_model_design.md` Section 4.

## Result

[paste match_rate from test output]

## Mismatch breakdown

[paste mismatch_categories dict from test output]

## Decision per kickoff brief Section 4

- If match_rate >= 0.80: **proceed to Day 5-7** (real Phase 4 + sun/planet collisions).
- If match_rate < 0.80 after one debug day: **surface and re-decide** whether to continue C or pivot.

[fill in the actual decision once test runs]

## What's next

- Day 5-7: real Phase 4 (advance fleets, sun collision check, planet collision check).
- Filter remains static-only until Day 7-9.
```

- [ ] **Step 3: Commit the iteration log (and any in-flight fixes)**

```bash
git status -s
git add docs/iteration_logs/2026-05-05-sim-day-3-5-gate.md
git commit -m "$(cat <<'EOF'
docs(sim): record Day 3-5 gate result + next-step decision

Captures match rate, top mismatch categories, and the go/no-go decision
per kickoff brief Section 4. Plan C Day 3-5 closed; Day 5-7 is the
next active sub-plan.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

**Spec coverage check (against kickoff brief Section 3 + master design doc Section 4):**

- ✅ `validator.validate()` lands first with `state_diff` + categorization → Tasks 1-2.
- ✅ Phase 3 (production) → Task 3.
- ✅ Phase 6 (combat) via `world.resolve_arrival_event` → Task 4.
- ✅ Phase 2 (apply actions, spawn half) using `validate_move` → Task 5.
- ✅ Phase 4 interim stub borrowing world.py for ETA → Task 6.
- ✅ Phase 0 no-op (comets filtered) → Task 6.
- ✅ Per-phase property tests + validator integration → Tasks 3-7.
- ✅ Scenario filter for Day 3-5 → Task 8 (filter_day_3_5_scenarios).
- ✅ ≥80% match rate gate → Task 8.
- ✅ Document result + decision → Task 9.

**Placeholder scan:** none. All commands concrete; all code complete.

**Type consistency:**
- `combat_lists: dict[int, list]` shape consistent (key = planet.id, value = list of ArrivalEvent) across Tasks 4, 6.
- `state_diff` returns `dict[str, int]` consistently across Tasks 1, 2.
- `gate_categories: set[str] | None` parameter named consistently in Tasks 2, 8.

**Gap noted:** Task 5 sets `target_planet_id=-1` for new fleets; Task 6 leaves them in-flight when target is unresolved. This means a fleet launched in Task 5 will NEVER arrive in Day 3-5 simulation, contributing to fleet-count-mismatch. Day 5-7 (real Phase 4) needs to derive target by walking the fleet's straight-line path against planets — that's out of scope for this plan.

**Out of plan (deliberate):**
- Phase 1 (comet spawn) — design doc Section 5 risk #2; intentionally never implemented at simulator level.
- Phase 5 (rotation + sweep) — Day 7-9.
- Real Phase 4 (advance positions, sun + planet collisions) — Day 5-7.
- Numba/JAX perf optimization — Days 14-16, only after Day 14 fidelity gate.
