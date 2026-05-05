"""Forward-model validation harness.

Per `docs/research_documents/mcts_forward_model_design.md` Section 3.3,
the validator does two things:

1. **Scenario generation** — runs real env episodes, captures
   `(state_t, actions_t, state_{t+1})` triples.
2. **Validation** — for each triple, runs `Simulator.step(state_t, actions_t)`,
   compares to `state_{t+1}`, reports match-rate and a categorized mismatch
   summary.

Day-1 finding (env-state-extraction agent, 2026-05-04): kaggle_environments
exposes the env's full internal state on `env.steps[i][0].observation`, AND
state can be INJECTED into a fresh env by directly mutating those attributes.
Round-trip is byte-perfect except at comet-spawn boundaries (steps 50, 150,
250, 350, 450) where Python's global RNG drives spawn ship counts.

This means we can ALSO use the env itself as the reference forward model
for MCTS (Path C-env per design doc Section 4.5). The functions
`extract_state_and_actions` and `inject_state_and_step` below support both
paths.
"""

from __future__ import annotations

import copy
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .action import Action
from .simulator import Simulator
from .state import (
    SimCometGroup,
    SimConfig,
    SimFleet,
    SimPlanet,
    SimState,
)

__all__ = [
    "ForwardModelValidator",
    "ValidationReport",
    "ValidationTriple",
    "extract_state_and_actions",
    "filter_day_3_5_scenarios",
    "filter_day_5_7_scenarios",
    "inject_state_and_step",
    "state_diff",
]


# Comet-spawn step indices (env L27). These transitions are non-deterministic
# (RNG-driven ship counts) and should be excluded from strict validation.
COMET_SPAWN_STEPS = frozenset({50, 150, 250, 350, 450})


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
    triples: list["ValidationTriple"],
) -> list["ValidationTriple"]:
    """Filter triples to the Day 3-5 gate set.

    REVISED from kickoff brief Section 3.3 after empirical findings (2026-05-05):
    real games have ~28 planets with most rotating; the original "all-static"
    requirement passed only ~0.22% of triples, all of which were the degenerate
    step-0 empty-world case. Replaced with the conditions that actually identify
    states our minimal Day 3-5 simulator can match end-to-end:

      - state_t.step >= 1 (skip empty initial observation; env populates at step 1)
      - state_t has no comet groups present (Phase 0 stub is a no-op)
      - state_t has no fleets in flight (Phase 4 stub doesn't advance)
      - state_t.step NOT in COMET_SPAWN_STEPS (Phase 1 unimplemented)
      - state_t.step + 1 NOT in COMET_SPAWN_STEPS (next-state diverges)
      - 2P games only (state_t.config.num_agents == 2)

    Rotation (Phase 5) is now skipped via Simulator.skip_phase_5; planet x/y
    will diverge from env but state_diff doesn't check x/y so this is fine.
    Comet expirations (Phase 0) are not in scope; the no-comets filter avoids them.
    """
    out: list[ValidationTriple] = []
    for tri in triples:
        s = tri.state_t
        if s.step < 1:
            continue
        if s.comet_groups:
            continue
        if s.fleets:
            continue
        if s.config.num_agents != 2:
            continue
        if s.step in COMET_SPAWN_STEPS:
            continue
        if (s.step + 1) in COMET_SPAWN_STEPS:
            continue
        out.append(tri)
    return out


def filter_day_5_7_scenarios(
    triples: list["ValidationTriple"],
) -> list["ValidationTriple"]:
    """Filter triples to the Day 5-7 gate set.

    Broadens Day 3-5 by ALLOWING state_t to have fleets in flight (real
    Phase 4 now handles fleet movement + collisions). Phase 5 (rotation +
    sweep) is still skipped, so rotation-induced mismatches remain
    expected; the gate-categories tuning happens in the integration test.

    Keeps a triple iff ALL hold:
      - state_t.step >= 1
      - state_t.comet_groups == []   (Phase 0 stub is no-op)
      - state_t.config.num_agents == 2
      - state_t.step NOT in COMET_SPAWN_STEPS
      - state_t.step + 1 NOT in COMET_SPAWN_STEPS

    Removed (vs Day 3-5):
      - state_t.fleets == []   (now allowed; real Phase 4 handles them)
    """
    out: list[ValidationTriple] = []
    for tri in triples:
        s = tri.state_t
        if s.step < 1:
            continue
        if s.comet_groups:
            continue
        if s.config.num_agents != 2:
            continue
        if s.step in COMET_SPAWN_STEPS:
            continue
        if (s.step + 1) in COMET_SPAWN_STEPS:
            continue
        out.append(tri)
    return out


# ---------------------------------------------------------------------------
# Env <-> SimState conversion (private helpers)
# ---------------------------------------------------------------------------


def _env_dict_to_simstate(state_dict: dict, num_agents: int) -> SimState:
    """Convert env's Struct-compatible dict to typed SimState.

    Env planet shape: [id, owner, x, y, radius, ships, production]
    Env fleet shape: [id, owner, x, y, angle, from_id, ships]
    Env comet group: {'planet_ids': [...], 'paths': [...], 'path_index': int}
    """
    comet_pid_set = set(state_dict["comet_planet_ids"])

    planets = [
        SimPlanet(
            id=p[0], owner=p[1], x=p[2], y=p[3], radius=p[4],
            ships=float(p[5]), production=p[6],
            is_comet=p[0] in comet_pid_set,
        )
        for p in state_dict["planets"]
    ]
    initial_planets = [
        SimPlanet(
            id=p[0], owner=p[1], x=p[2], y=p[3], radius=p[4],
            ships=float(p[5]), production=p[6],
            is_comet=p[0] in comet_pid_set,
        )
        for p in state_dict["initial_planets"]
    ]
    fleets = [
        SimFleet(
            id=f[0], owner=f[1], x=f[2], y=f[3], angle=f[4],
            from_planet_id=f[5],
            target_planet_id=-1,         # env doesn't track; sim derives via collision
            ships=f[6],
            spawned_at_step=-1,          # env doesn't track per-fleet
        )
        for f in state_dict["fleets"]
    ]
    comet_groups = [
        SimCometGroup(
            planet_ids=list(g["planet_ids"]),
            paths=[[tuple(pt) for pt in path] for path in g["paths"]],
            path_index=g["path_index"],
        )
        for g in state_dict["comets"]
    ]

    return SimState(
        step=state_dict["step"],
        planets=planets,
        fleets=fleets,
        comet_groups=comet_groups,
        angular_velocity=state_dict["angular_velocity"],
        next_fleet_id=state_dict["next_fleet_id"],
        config=SimConfig(num_agents=num_agents),
        initial_planets=initial_planets,
    )


def _simstate_to_env_dict(state: SimState) -> dict:
    """Convert typed SimState back to env's Struct-compatible dict (for injection)."""
    return {
        "step": state.step,
        "planets": [
            [p.id, p.owner, p.x, p.y, p.radius, p.ships, p.production]
            for p in state.planets
        ],
        "fleets": [
            [f.id, f.owner, f.x, f.y, f.angle, f.from_planet_id, f.ships]
            for f in state.fleets
        ],
        "comets": [
            {
                "planet_ids": list(g.planet_ids),
                "paths": [[list(pt) for pt in path] for path in g.paths],
                "path_index": g.path_index,
            }
            for g in state.comet_groups
        ],
        "comet_planet_ids": [p.id for p in state.planets if p.is_comet],
        "initial_planets": [
            [p.id, p.owner, p.x, p.y, p.radius, p.ships, p.production]
            for p in state.initial_planets
        ],
        "angular_velocity": state.angular_velocity,
        "next_fleet_id": state.next_fleet_id,
    }


# ---------------------------------------------------------------------------
# Public extraction / injection (verified by env-state-extraction agent)
# ---------------------------------------------------------------------------


def extract_state_and_actions(
    env: Any, step_idx: int
) -> tuple[SimState, dict[int, list[Action]]]:
    """Extract typed SimState at `step_idx` plus actions submitted to PRODUCE step_idx+1.

    `env` is a kaggle_environments Environment that has been .run() to completion.
    Per env L671-677, all per-agent observations share the same internal lists,
    so reading from agent 0 is sufficient.

    Action indexing convention: `env.steps[step_idx + 1][p].action` is the action
    player p submitted while the env was in state step_idx.
    """
    snap = env.steps[step_idx]
    obs = snap[0].observation
    n_agents = len(snap)

    state_dict = {
        "step": obs.step,
        "planets": copy.deepcopy(list(obs.planets)),
        "fleets": copy.deepcopy(list(obs.fleets)),
        "comets": copy.deepcopy(list(obs.comets)),
        "comet_planet_ids": list(obs.comet_planet_ids),
        "initial_planets": copy.deepcopy(list(obs.initial_planets)),
        "angular_velocity": obs.angular_velocity,
        "next_fleet_id": obs.next_fleet_id,
    }
    sim_state = _env_dict_to_simstate(state_dict, num_agents=n_agents)

    actions: dict[int, list[Action]] = {}
    if step_idx + 1 < len(env.steps):
        next_snap = env.steps[step_idx + 1]
        for p in range(n_agents):
            raw = next_snap[p].action
            if raw:
                actions[p] = [Action.from_env_format(move) for move in raw]
            else:
                actions[p] = []
    else:
        actions = {p: [] for p in range(n_agents)}

    return sim_state, actions


def inject_state_and_step(
    state: SimState, actions: dict[int, list[Action]]
) -> Any:
    """Inject `state` into a fresh env, submit `actions`, return env after one step.

    The returned env's `state[0].observation` carries the new state. Round-trip
    is byte-perfect with the original env except at comet-spawn boundaries
    (where Python's global RNG drives spawn ship counts).

    Critical quirk (env-state-extraction agent's finding #1): kaggle_environments
    overwrites `obs.step = len(env.steps)` inside .step(), but reads `obs.step`
    BEFORE that overwrite for rotation math. So we must set the correct step
    on injection; the env will use it for this step then overwrite for the next.
    """
    from kaggle_environments import make

    n_agents = state.config.num_agents
    env = make("orbit_wars", debug=True)
    env.reset(n_agents)

    state_dict = _simstate_to_env_dict(state)
    for i in range(n_agents):
        o = env.state[i].observation
        o.planets = copy.deepcopy(state_dict["planets"])
        o.fleets = copy.deepcopy(state_dict["fleets"])
        o.comets = copy.deepcopy(state_dict["comets"])
        o.comet_planet_ids = list(state_dict["comet_planet_ids"])
        o.initial_planets = copy.deepcopy(state_dict["initial_planets"])
        o.angular_velocity = state_dict["angular_velocity"]
        o.next_fleet_id = state_dict["next_fleet_id"]
        o.step = state_dict["step"]

    env_actions = [
        [a.to_env_format() for a in actions.get(p, [])]
        for p in range(n_agents)
    ]
    env.step(env_actions)
    return env


# ---------------------------------------------------------------------------
# state_diff — categorized mismatch detection
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ValidationTriple, ValidationReport, ForwardModelValidator
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ValidationTriple:
    """One (state, actions, next_state) data point captured from the real env.

    Frozen by convention but not @frozen: SimState and dict[int, list[Action]]
    contain mutable fields (lists), so dataclass-level freezing wouldn't help.
    """

    state_t: SimState
    actions_t: dict[int, list[Action]]
    expected_state_t1: SimState
    source_seed: int
    source_step: int
    crosses_comet_spawn: bool = False


@dataclass(slots=True)
class ValidationReport:
    """Aggregated validation results for a batch of triples."""

    n_total: int
    n_match: int
    mismatches: list[tuple[ValidationTriple, dict]] = field(default_factory=list)
    mismatch_categories: dict[str, int] = field(default_factory=dict)

    @property
    def match_rate(self) -> float:
        return self.n_match / self.n_total if self.n_total else 0.0


@dataclass(slots=True)
class ForwardModelValidator:
    """Generates scenarios from real env and validates a Simulator against them."""

    simulator: Simulator
    pos_tolerance: float = 0.1
    ship_tolerance: int = 0
    skip_comet_spawn: bool = True

    def collect_scenarios(
        self,
        seeds: list[int],
        opponent_pool: list[Callable | str],
        opponent_combos: list[tuple] | None = None,
        max_steps_per_episode: int | None = None,
    ) -> list[ValidationTriple]:
        """Run real env episodes and extract per-step triples.

        For each (seed, combo) pair, runs one episode and yields one triple per
        valid transition. If `opponent_combos` is None, uses opponent_pool[0]
        repeated for the env's default agent count (2P).
        """
        from kaggle_environments import make

        if opponent_combos is None:
            opponent_combos = [(opponent_pool[0], opponent_pool[0])]

        triples: list[ValidationTriple] = []
        for seed in seeds:
            for combo in opponent_combos:
                env = make("orbit_wars", debug=True, configuration={"seed": seed})
                env.run(list(combo))
                last_step = len(env.steps) - 1
                end = min(last_step, max_steps_per_episode or last_step)
                for step_idx in range(end):
                    state_t, actions_t = extract_state_and_actions(env, step_idx)
                    expected_state, _ = extract_state_and_actions(env, step_idx + 1)
                    triples.append(ValidationTriple(
                        state_t=state_t,
                        actions_t=actions_t,
                        expected_state_t1=expected_state,
                        source_seed=seed,
                        source_step=step_idx,
                        crosses_comet_spawn=(state_t.step + 1) in COMET_SPAWN_STEPS,
                    ))
        return triples

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

    def save_scenarios(self, triples: list[ValidationTriple], path: Path) -> None:
        """Pickle triples to disk so we can re-run validation without re-extraction."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(triples, f)

    def load_scenarios(self, path: Path) -> list[ValidationTriple]:
        """Load previously-saved triples."""
        with path.open("rb") as f:
            return pickle.load(f)
