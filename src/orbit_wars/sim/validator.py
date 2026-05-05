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
    "inject_state_and_step",
]


# Comet-spawn step indices (env L27). These transitions are non-deterministic
# (RNG-driven ship counts) and should be excluded from strict validation.
COMET_SPAWN_STEPS = frozenset({50, 150, 250, 350, 450})


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

    def validate(self, triples: list[ValidationTriple]) -> ValidationReport:
        """Run Simulator.step on each triple and compare to expected.

        Currently only checks Simulator-side. Once Path C-env vs Path C-original
        is decided, can also support env-as-reference validation
        (use inject_state_and_step as the reference instead of triple's expected).

        Lands progressively as Simulator phases come online (Days 3-11).
        """
        raise NotImplementedError(
            "validate() depends on Simulator.step being implemented (Days 3-11)."
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
