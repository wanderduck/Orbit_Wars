# MCTS Forward-Model + Validation Harness — Design Sketch

**Status:** draft, 2026-05-04. Authored as the kill-switch for path C (MCTS) before
investing weeks of engineering. This document describes (1) the architecture, (2) the
build order with explicit go/no-go gates, and (3) the time/risk envelope.

## 0. Why this document exists

Per ongoing strategy discussion, we're committing to **A + C in parallel** (heuristic
tuning + MCTS). MCTS's central risk is **forward-model fidelity** — the
"off-by-N rotation bug in v1.2" (CLAUDE.md) was a single subtle env behavior that took
days to find. A custom simulator that drifts from the real env causes MCTS to
confidently choose moves that look great in simulation but fail in production —
worse than the heuristic, with no obvious symptoms.

This design therefore puts the **validation harness BEFORE the MCTS algorithm**.
Build order is: faithful step simulator → validation harness → ≥99% match gate →
THEN tree search on top. If the simulator can't pass the gate within ~5 working
days, MCTS is dead and we fall back to A (and possibly B).

## 1. Goal

Produce two artifacts:

1. **`Simulator`** — a deterministic next-state function:
   `step(state, actions: dict[player_id, list[Action]]) -> state`.
   Exactly mirrors the kaggle_environments orbit_wars env's per-turn semantics.

2. **`ForwardModelValidator`** — automated test harness:
   Generates ~thousands of (state_t, actions_t, state_{t+1}) triples by running real
   env episodes, then confirms `Simulator.step(state_t, actions_t) == state_{t+1}`
   for ≥99% of triples. Mismatches dumped to a report for debugging.

**Definition of done:** validator reports ≥99% exact-match on planet ownership,
ship counts (integer), fleet positions (within ε=0.1 units), and comet states across
≥1000 random scenarios drawn from ≥10 random seeds and ≥3 random opponents.

## 2. What we already have (and don't have to build)

`src/orbit_wars/` contains a substantial substrate. The simulator should EXTEND
these, not replace them:

| Module | What it provides | Reuse for simulator? |
|--------|-----------------|---------------------|
| `geometry.py` | All env constants (BOARD=100, SUN at (50,50) r=10, MAX_SPEED=6, ROTATION_RADIUS_LIMIT=50, LAUNCH_CLEARANCE=0.1), `fleet_speed()` formula, sun-segment intersection, safe-angle solver | YES — verbatim |
| `rotation.py` | `predict_planet_position()` — exact rotation math | YES — verbatim |
| `world.py: resolve_arrival_event` | Faithful E1 §Combat port: top-2 cancel, mutual annihilation on tie, survivor vs garrison | YES — this IS the combat resolver |
| `world.py: _simulate_timeline` | Production+combat per-turn for ONE planet (single-agent forecast) | NO — wrong shape, single-planet/single-actor only |
| `world.py: WorldModel` | Multi-planet forecast cache built from observation; assumes opponents do nothing | NO — we need a step function, not a forecast |
| `world.py: _build_arrival_ledger` | Projects in-flight fleets to their target planets | PARTIAL — known-buggy (skips moving-planet sweeps per its own docstring) |
| `world.py: path_collision_predicted` | Walks a fleet's trajectory turn-by-turn checking collisions with other planets at predicted positions | YES — needed for fleet sweep handling in the simulator's movement phase |
| `state.py` | `ObservationView`, `Planet`, `Fleet` typed wrappers | YES — internal state representation |

**What's missing** (the actual simulator work):

- A multi-agent step function (apply actions from all 4 players, then advance one turn).
- Comet expiration / spawn (CLAUDE.md mentions phase 1; need to find env source).
- Planet rotation as a STATE MUTATION (current `predict_planet_position` is a query, not a step).
- Fleet position update as a state mutation (current `WorldModel` projects ETAs, doesn't move fleets in space).
- Phase-6 fleet-sweep handling (a moving planet rotates INTO a fleet → combat resolves there).
- Action validation matching env (insufficient ships, non-owned source, etc).

## 3. Architecture

```
src/orbit_wars/sim/                          (NEW package)
├── __init__.py
├── state.py       # SimState dataclass — full mutable state
├── action.py      # Action dataclass; validation
├── simulator.py   # Simulator class with .step()
└── validator.py   # ForwardModelValidator + scenario generator

src/tools/
└── validate_simulator.py   # CLI: orbit-play sim-validate
```

### 3.1 `SimState` — the mutable state

Mirrors the env's internal state, not the player observation. Fields:

```python
@dataclass(slots=True)
class SimState:
    step: int                               # current turn (1-indexed)
    planets: list[SimPlanet]                # all planets including comet-aliased
    fleets: list[SimFleet]                  # all in-flight fleets
    comet_groups: list[SimCometGroup]       # active comet groups (paths + indices)
    angular_velocity: float                 # global, fixed per game
    config: SimConfig                       # episode_steps, etc.
    _initial_planets: list[SimPlanet]       # frozen snapshot for rotation reference

@dataclass(slots=True)
class SimPlanet:
    id: int
    x: float; y: float
    radius: float
    owner: int                              # -1 = neutral
    ships: float
    production: int
    is_comet: bool

@dataclass(slots=True)
class SimFleet:
    id: int                                 # globally unique within episode
    owner: int
    from_planet_id: int
    target_planet_id: int                   # the planet the player AIMED at
    x: float; y: float
    angle: float
    ships: int
    spawned_at_step: int
```

Note: a fleet's "target" matters for combat (fleet must collide with target's
predicted position), but the env may also have a fleet collide with a NON-target
planet via phase 6 (moving planet sweeps). Both must be handled.

### 3.2 `Simulator.step(state, actions)`

Per-turn phase order (verified from env source `.venv/.../orbit_wars.py`, lines 419-711):

```python
def step(self, state: SimState, actions: dict[int, list[Action]]) -> SimState:
    new_state = deepcopy(state)
    new_state.step += 1

    self._phase_0_comet_expiration(new_state)       # env L419-439: remove comets where path_index >= len(path)
    self._phase_1_comet_spawn(new_state)            # env L441-477: spawn at COMET_SPAWN_STEPS=[50,150,250,350,450]
    self._phase_2_apply_actions(new_state, actions) # env L479-512: validate + spawn fleets, increment next_fleet_id
    self._phase_3_production(new_state)             # env L514-517: planet[5] += planet[6] for owner != -1
    self._phase_4_advance_fleets(new_state)         # env L519-551: move fleets, check sun & planet collisions
    self._phase_5_rotate_planets(new_state)         # env L553-627: rotate orbiting planets; advance comet path; sweep
    self._phase_6_resolve_combat(new_state)         # env L630-669: drain combat_lists into resolve_arrival_event
    # Phase 7 (obs sync) and 8 (termination/reward) — handled by validator, not simulator

    return new_state
```

Each phase is a small, separately testable method. Combat aggregator is shared
state populated by Phase 4 (fleet hits planet) AND Phase 5 (planet sweeps fleet),
drained in Phase 6.

### 3.3 Critical env quirks the simulator MUST replicate

These come from the env-source review and are easy to get wrong:

1. **Sun collision threshold is `< SUN_RADIUS` (10.0). NO safety margin.**
   Our `geometry.py` uses `SUN_RADIUS + SUN_SAFETY (1.5)` — that's the heuristic's
   path-planner being conservative, NOT what the env enforces. The simulator must
   use bare `SUN_RADIUS` for fleet movement collision detection.

2. **Planet collision threshold is `< planet.radius`. NO clearance margin.**
   Same gotcha. Our `path_collision_predicted` adds `LAUNCH_CLEARANCE` (0.1) for
   the heuristic; the env uses bare `planet.radius`. Simulator must match env.

3. **Garrison does NOT participate in inter-fleet combat.** The "top-2 cancel"
   resolves between ARRIVING FLEETS only. The survivor then fights the garrison.
   This is what `world.py: resolve_arrival_event` already does correctly. Don't
   accidentally include the garrison in the top-2 sort.

4. **Exact tie at top → 0 survivors, planet undamaged.** If `top_ships == second_ships`
   exactly, `survivor_ships = 0` and the planet takes no damage and doesn't change
   ownership. This is in `world.py` already. Be precise with the comparison.

5. **Production applies to ALL owned planets including captured comets**, BEFORE
   fleet movement. So a planet captured last turn produces this turn (same-turn
   production timing matters for reward calculation in the final 2 turns).

6. **Comet ships at spawn = `min(randint(1,99), randint(1,99), randint(1,99), randint(1,99))`**.
   Four independent draws from Python's global random state, taking the min. This
   is RNG-coupled to the env's prior random consumption. **Simulator cannot
   reproduce comet spawns deterministically without replaying the env's full RNG
   stream.** See risk #2 below for mitigation.

7. **Comet `path_index` starts at -1.** Spawn places comet at `(-99, -99)`. The
   first movement increments `path_index` to 0 and places it at `path[0]`. Sweep
   is skipped for the first placement (the `old_pos[0] >= 0` guard).

8. **Sweep collision uses point-vs-segment** (fleet position vs planet's swept path).
   Phase 4 collision uses segment-vs-point (fleet's path vs static planet position).
   These are different geometric tests; don't conflate.

9. **Reward is BINARY +1/-1 per env L679-711.** Sum ships from owned planets +
   in-flight fleets per player; max-score gets +1; ALL OTHERS (including ties at
   top) get -1. There is no graduated 2nd/3rd/4th reward. The user's "Kaggle 4P
   = 3 losers all place 2nd" comment refers to the EXTERNAL Elo system, not the
   env reward.

10. **Episode terminates when `step >= episodeSteps - 2`** (2 steps early), or
    when ≤1 player has any planet/fleet remaining.

11. **Invalid actions are silently rejected.** No error, no penalty. Five
    validation checks: action is list, move has 3 elements, source planet exists,
    source is player-owned, source has ≥ ships requested AND ships > 0. Any
    failure → move skipped without trace.

12. **Fleet IDs are globally unique within an episode** via `next_fleet_id`
    counter. Simulator must increment this counter on every accepted launch.

### 3.3 `ForwardModelValidator`

Two phases: scenario generation, then validation.

**Scenario generation** — capture real (state, action, next-state) triples from
random env runs:

```python
def collect_scenarios(n_episodes: int, seeds: list[int],
                      opponent_pool: list[Callable]) -> list[ValidationTriple]:
    triples = []
    for seed in seeds:
        for opp_combo in sample_opponent_combos(opponent_pool, ...):
            env = make("orbit_wars", configuration={"seed": seed}, debug=True)
            env.run(opp_combo)  # 2P or 4P
            for step_idx in range(len(env.steps) - 1):
                state_t = extract_internal_state(env, step_idx)
                actions_t = extract_actions(env, step_idx)
                state_t1 = extract_internal_state(env, step_idx + 1)
                triples.append(ValidationTriple(state_t, actions_t, state_t1))
    return triples
```

The interesting part is `extract_internal_state`: kaggle_environments stores per-
agent observations in `env.steps`, but the env's INTERNAL state (where fleets
actually are, comet path indices, etc.) lives in env.state[0].observation or
similar. Need to reverse-engineer the exact attribute path. Per CLAUDE.md the
agent function only sees the OBSERVATION; the env keeps richer state internally
that we may need to mock by composing observations from all 4 players.

**Validation**:

```python
def validate(triples: list[ValidationTriple], simulator: Simulator) -> ValidationReport:
    matches = 0; mismatches = []
    for tri in triples:
        actual = simulator.step(tri.state_t, tri.actions_t)
        diff = state_diff(actual, tri.expected_state_t1, tol_pos=0.1)
        if not diff:
            matches += 1
        else:
            mismatches.append((tri, diff))
    return ValidationReport(
        match_rate=matches / len(triples),
        n_total=len(triples),
        mismatches=mismatches[:50],       # cap for report size
        mismatch_categories=categorize(mismatches),
    )
```

Mismatch categorization: ownership-flip wrong, ship-count off-by-N, fleet position
drift, comet missed, etc. This is the diagnostic loop — fix the most-frequent
category, re-run, repeat.

## 4. Build order with kill-switches

Each step has a CONCRETE GO/NO-GO at the end. If a gate fails after reasonable
debugging effort, MCTS development stops.

### Day 1-2: Scenario extractor (the harness comes first)

Goal: working `collect_scenarios()` that produces triples we can `pickle` and
re-load. Validator can be a stub that just prints `len(triples)`.

**Gate:** can extract ≥1000 triples from random episodes; pickled file loads;
each triple has well-formed state_t, actions_t, state_t1. **If this fails:** the
env's internal state is harder to extract than we thought. Spend 1 more day
trying alternate extraction paths (env.steps[i] vs env.state vs env.specification).
If still stuck after day 3, switch to PATH B (RL doesn't need internal state
extraction — env.step is the simulator).

### Day 3-5: Minimal Simulator

Implement phases 3-4-7 only (apply actions, production, combat). Skip rotation
(treat all planets as static), skip comets (filter scenarios that have them),
skip fleet movement (use the env's straight-line ETA from the existing world.py).

**Gate:** ≥80% match rate on STATIC-PLANET-ONLY 2P scenarios with NO COMETS.
This proves the combat resolver and action handling are correct. **If this
fails:** combat math is wrong despite the existing port being labeled "faithful."
Need to read env source carefully and find the divergence. Should take <1 day.

### Day 5-7: Add fleet movement + sun collision

Implement phase 5 (advance fleets). Add sun-collision check (fleets whose new
position would be inside sun + safety → destroyed).

**Gate:** ≥90% match rate on STATIC-PLANET-ONLY scenarios (now with realistic
fleet propagation). **If this fails:** fleet propagation diverges (probably an
off-by-one in step timing — does the env apply movement before or after combat?).

### Day 7-9: Add planet rotation + phase-6 fleet sweep

Implement phase 6 (rotate planets, check whether moving planets sweep into
existing fleets). This is the trickiest phase per CLAUDE.md.

**Gate:** ≥95% match rate on FULL scenarios EXCEPT comets. **If this fails:**
the env's collision-detection geometry is different from what `path_collision_predicted`
implements. Need to align them.

### Day 9-11: Add comets

Implement phase 1 (expiration: comet at end of path → remove, garrison vanishes)
and phase 2 (spawn — likely deterministic based on episode-seed RNG, may need to
extract the env's comet-spawn logic verbatim).

**Gate:** ≥99% match rate on FULL random scenarios (2P + 4P, all opponents,
all 500 turns). **If this fails:** comet behavior is something subtle. Up to
3 more days of debugging. Hard cutoff at day 14: if ≥99% gate cannot be met by
end of week 2, MCTS is dead.

### Day 14: GO/NO-GO decision

Validator report: ≥99% match across 1000+ random scenarios? Then proceed to
MCTS algorithm (separate design doc). Otherwise, formal abandonment of C; pivot
to A (continue tuning) or A+B (add RL).

## 4.5 Path C-env alternative (NEW — supersedes much of Section 4)

**Discovered 2026-05-04 by env-state-extraction agent.** kaggle_environments
exposes the env's full internal state on `env.steps[i][0].observation` (no
private internals needed) AND supports state INJECTION via direct attribute
mutation: `env.state[i].observation.<field> = value`. Round-trip
(extract → inject → step → compare) is byte-perfect except at the 5
comet-spawn boundaries.

**Implication:** the custom Python simulator (Section 3.2) may not be needed.
We can use the env itself as the MCTS forward model. Per `validator.py`,
working extraction + injection are now in the codebase
(`extract_state_and_actions`, `inject_state_and_step`).

### 4.5.1 Two paths now

- **Path C-env (try first):** MCTS rollouts call `inject_state_and_step()`
  directly. Forward model is the env itself — 100% faithful by construction.
  Gate is **throughput**, not fidelity. No Numba/JAX needed for correctness.
- **Path C-original (fallback):** the design in Sections 3 + 4 (custom Python
  simulator + ≥99% match gate). Only triggered if Path C-env's throughput is
  too low.

### 4.5.2 Path C-env build order (revised)

| Day | Deliverable | Gate |
|----:|-------------|------|
| 1   | Scenario extractor + extract/inject in validator.py | DONE — see `src/orbit_wars/sim/validator.py` |
| 2   | Perf probe (`tools/sim_perf_probe.py`) | inject+step throughput ≥300 rollouts/turn @ depth 10 |
| 3-7 | MCTS algorithm proper (root-MCTS with heuristic-guided rollouts) | beats heuristic in N=100 self-play |
| 7-9 | 4P opponent modeling (heuristics in seats 1-3) | improves vs 4P bestv4 spot-check |
| 9-12 | Local tournament + Kaggle submission | ladder μ vs bestv4 |
| **Total** | **~12 days** | (vs ~20+ days for Path C-original) |

### 4.5.3 When to fall back to Path C-original

- Day-2 perf probe result <100 rollouts/turn at depth 10: forced to Path C-original immediately
- 100-300 rollouts/turn: try Path C-env first, watch for shallow-search symptoms during MCTS development
- ≥300 rollouts/turn: Path C-env is the path; Path C-original is shelved

### 4.5.4 RESOLUTION (2026-05-04 perf probe)

**Path C-env is NOT viable. Path C-original is required.**

Decomposed perf measurement on this machine (state size: 28 planets, 3 fleets):

```
make() alone:                 41ms  (one-time, amortizable across episode)
make() + reset():             77ms  (one-time per turn boundary)
inject only:                  ~8ms additional (per rollout)
env.step() alone (env reused): 4.48ms  (THE BOTTLENECK)

Best-case projected per rollout (1 inject + 10 steps):  ~53ms
Best-case rollouts/turn at 700ms budget:                ~13
```

**Why env.step() is so slow:** env does multi-agent observation syncing
(env L671-677: full deepcopy of state lists for each of N agents), schema
validation per call, and interpreter loop overhead. None of this is
necessary for MCTS rollouts. A custom Python simulator stripped of this
machinery should be 50-200× faster.

The env-source agent's earlier estimate of 0.1ms/step was wrong by 45×.
Estimating step cost without measurement is unreliable for this workload.

**Decision:** proceed with Path C-original (Section 4 build order, custom
Python simulator with ≥99% match gate). The env-as-simulator option is
dead until and unless we find a way to bypass env's bookkeeping (likely
not possible without modifying kaggle_environments).

The extraction + injection code in `validator.py` is STILL useful — it
becomes the validator's reference for "what does the env produce" comparisons
during the Path C-original build. It's not wasted work.

### 4.5.4 What remains unchanged

- The `Simulator` class scaffold in `src/orbit_wars/sim/simulator.py` is preserved as the Path C-original option (raises NotImplementedError; only built if Path C-env is unviable)
- The `SimState` typed schema is used by both paths
- Critical env quirks (Section 3.3) still matter — they're embedded in the env, but knowledge of them informs how we configure injection (e.g., `obs.step` overwrite quirk caught by the agent)
- The Day-12 deadline math still holds with margin

## 5. Risks and unknowns

1. **`extract_internal_state` is the unknown unknown.** kaggle_environments may
   not expose enough state through public APIs. We may need to reverse-engineer
   `env.state[i]` internals. Mitigation: investigation spike on day 1 alone.

2. **Comet spawn RNG (CONFIRMED PROBLEM).** Env source review confirms comet
   spawn ships are `min(randint(1,99) × 4)` drawn from Python's global random
   state at steps [50, 150, 250, 350, 450]. The env's RNG consumption between
   spawns is also non-trivial (planet-rotation RNG, etc), so reproducing the
   exact spawn ship-count requires replaying the env's full RNG history from
   episode start.

   **Mitigation: don't simulate comet spawn.** The simulator's `_phase_1_comet_spawn`
   should be a NO-OP. Validation triples that span a spawn boundary (turns 50,
   150, 250, 350, 450) get filtered out, OR the validator manually injects the
   env's actual spawned comets into the next-state expected output. This
   sacrifices ~1% of validation triples (5 spawn boundaries × ~2 turns of
   blast radius / 500 turns) but keeps the simulator deterministic given a
   start state.

   This is acceptable for MCTS because at MCTS-search time, we know the current
   step number — we can decide "if any rollout would cross step 50, treat
   comet spawn as a fixed expected event using the comets already visible in
   the observation, or cut the rollout short."

3. **Phase ordering ambiguity.** The world.py docstring says
   "comet expiration → comet spawn → fleet launch → production → fleet movement
   → planet rotation/comet movement → combat resolution." But the EXACT order of
   sub-mutations within a phase matters (e.g., does rotation precede the sweep
   check or follow it?). Env-source agent's findings will resolve this.

4. **State equality definition.** Floats need tolerance, ints don't. Fleet ID
   assignment — does the env give fleets globally unique IDs we can match? Or
   do we have to identify them by (origin, target, owner, spawn_step) tuple?

5. **MCTS time budget.** Even if the simulator passes ≥99% match, it must also
   be FAST enough to run thousands of rollouts in ≤700ms per turn. Python's
   overhead is real. See Section 6 for the performance plan.

6. **The 4-player branching factor for MCTS.** Even with a perfect simulator,
   single-player MCTS in 4P games loses to opponent modeling errors. Plan to
   use the heuristic agent as the rollout/opponent policy. This is a separate
   design problem (later) but worth flagging now: MCTS in 4P FFA is hard
   research-wise. The simulator gates *existence*; the strategy gates *value*.

## 6. Performance — when and how to optimize

### 6.1 Throughput target

Competitive MCTS in this game class wants **≥1000 iterations per turn** for
useful search depth. Per-iteration cost ≈ 1 expansion step + K rollout steps;
with K=10 rollout depth that's ~11 simulator-steps per iteration. So target
simulator throughput is roughly **11,000 sim-steps per turn** = ~16,000 sim-steps
per second (after subtracting tree-traversal/MCTS overhead from the 700ms
budget).

Pure-Python sim step in this codebase is plausibly 0.5-2ms (rough estimate from
the heuristic's per-call profile, which exercises similar geometry). That gives
~500-2000 sim-steps/sec — **roughly 30-150× too slow**. Acceleration is
necessary, not optional.

### 6.2 Tool comparison for THIS workload

The simulator has variable-length structures (10 planets, 0-100 fleets, 0-2
comet groups), aggregation/sort in combat resolution, branching in collision
checks, and is called many times per turn. Three plausible accelerators:

| Tool | Engineering cost | Expected speedup | Maintainability | Fit to workload |
|------|-----------------|------------------|-----------------|----------------|
| **Numba** (`@jit`) | 1-2 days (decorators + minor refactor) | 10-50× | Stays Python; debug normal | **GOOD** — handles loops, branches, lists |
| **CuPy** | 3-5 days refactor to numpy arrays | <1× to 2× (overhead-dominated) | Awkward (numpy/CuPy switching) | **POOR** — small arrays, GPU launch overhead dominates |
| **JAX** (batched rollouts) | 2-4 weeks rewrite to JAX-pure code | 50-200× per batch (256 rollouts in parallel) | Hard (no Python branches, no `print` in jit, abstract traces) | **GOOD with rewrite, BAD without** |

**CuPy is the wrong tool here.** CuPy excels when you have one big numeric
array; we have many small heterogeneous structures. Single-step CuPy on
~10-element arrays is dominated by GPU kernel launch overhead (~50-100µs per
op). Net effect: probably slower than CPU Python. Skip.

**Numba is the cheap first step.** Decorator-based; preserves the natural
Python control flow (loops over fleets, branches in combat); supports lists
(via `numba.typed.List`); easy fallback (just remove `@jit`). Typical 10-50×
speedup gets us from ~500 sim-steps/sec to 5,000-25,000 — likely **enough to
hit the 16K target**.

**JAX is the heavy artillery.** Only worth the 2-4 week rewrite cost if Numba
caps out below the 1000-iter/turn target. The killer JAX play is
**leaf-parallelized MCTS**: run a batch of 256 leaf rollouts in parallel on
GPU per call. Used by AlphaGo Zero and modern MCTS implementations. Could give
50-200× wall-clock per batch. But: requires fixed-shape padded arrays
everywhere, branchless code (`jnp.where` instead of `if`), no Python list ops.
Combat resolution (sort + group + tie-branch) is JAX-hostile and has to be
rewritten as masked ops. Debugging is painful (traced functions don't `print`;
errors surface as cryptic XLA messages).

### 6.3 Why defer optimization until after the fidelity gate

1. **Correctness > speed.** A correct slow simulator is far better than a fast
   incorrect one. Validation is significantly harder for accelerated code (JAX
   traces are abstract; Numba's `@jit` errors point to compiled code, not
   source). Get the pure-Python sim to ≥99% env match FIRST, then optimize the
   validated implementation.

2. **Profile before optimizing.** The 0.5-2ms sim-step estimate is a guess.
   Actual hot path may be unexpected — `deepcopy` of state, the
   `path_collision_predicted` O(N planets × N turns) loop, combat aggregation,
   or just Python attribute access overhead. Decorating the wrong function is
   wasted effort.

3. **Algorithm matters more than raw speed.** The notebook MCTS we reviewed
   used **random rollouts** (worthless in this game) and got nowhere visible.
   Switching to heuristic-guided rollouts (use our existing strategy as the
   rollout policy) is probably worth more than 10× more iterations of random
   rollouts. Get the algorithm right, then optimize.

4. **JAX rewrite competes with the deadline.** 2-4 weeks of JAX work consumes
   30-60% of remaining time-to-deadline (50 days). If we hit the simulator
   gate at day 14 and immediately start a JAX rewrite, we lose ~half the
   remaining runway with no Kaggle results yet. Numba is 1-2 days; affordable.

### 6.4 Concrete performance plan

Insert two new days into the build order between the fidelity gate (day 14)
and MCTS algorithm work:

- **Day 14-15: Profile pure-Python simulator at the validated state.**
  Use `cProfile` on a representative MCTS-rollout-shaped workload (a script
  that calls `simulator.step()` 10,000 times with realistic state diversity).
  Identify hot path. Output: `docs/research_documents/sim_profile.md` with a
  flamegraph and top-10 functions by cumulative time.

- **Day 15-16: Numba pass on the hot path.** Decorate the top 2-3 hot
  functions; refactor minimally where needed (e.g., replace dict aggregation
  with `numba.typed.Dict` if needed). Re-run the validation harness — must
  still pass ≥99% match (Numba can't introduce bugs if it works at all, but
  numeric semantics may differ subtly for edge cases like NaN/inf).

- **Day 16: Re-profile.** If sim-step throughput ≥15K/sec on a typical state,
  proceed to MCTS algorithm work. Otherwise: decide whether (a) Numba more
  aggressively, (b) C/Cython rewrite of one critical function, or (c) JAX
  batched rewrite. The JAX decision needs explicit user signoff — it's
  multi-week.

This pushes the MCTS algorithm work from day 14 to day 16, but the perf step
is small (2 days) and saves us from building MCTS on top of an unusably-slow
simulator.

### 6.5 What I would NOT do

- **Don't reach for GPU first.** GPU-vs-CPU on small per-step workloads is
  rarely a win; the bottleneck is launch/transfer overhead. GPU pays off ONLY
  with batched parallelism (JAX `vmap` over many rollouts). And batched MCTS
  is its own design problem.

- **Don't write the simulator in JAX from day 1.** Even if we'd eventually
  want JAX, writing JAX-pure code from scratch is much harder than porting
  validated Python to JAX. Tracing through bugs in code that has never been
  run in pure Python is painful.

- **Don't rewrite in Cython prematurely.** Cython is a viable alternative to
  Numba (sometimes faster, more control) but has higher engineering cost (a
  separate build step, type annotations everywhere). Reach for Cython only if
  Numba leaves us within 2× of target throughput — at that level it can close
  the gap, but Numba's broader speedups are usually enough to skip Cython.

## 7. Time/effort envelope

Total elapsed: **2-3 weeks for working forward model**, IF everything passes
gates first try. Could be 4-5 weeks with debugging.

| Phase | Days | What kills the path |
|-------|------|---------------------|
| Scenario extraction | 1-2 | env state inaccessible after 3 days |
| Minimal sim | 1-3 | combat math wrong after 1 day debugging |
| Fleet movement | 1-2 | propagation phase order can't be matched |
| Rotation + sweep | 2-3 | env collision geometry can't be replicated |
| Comets | 2-3 | comet spawn RNG can't be reproduced (skip-spawn fallback) |
| **Fidelity gate** | **7-13** | hard kill at day 14 |
| Profile + Numba pass | 2 | sim too slow even with Numba; JAX rewrite needed (multi-week, requires user signoff) |
| MCTS algorithm | 5-7 | (separate doc; only starts after fidelity gate AND perf target met) |
| Tuning + Kaggle eval | 3-5 | (separate doc) |

Deadline math: today 2026-05-04, deadline 2026-06-23 = 50 days. Path C consumes
roughly 22-27 of those if all goes well (fidelity + perf + algorithm + tuning),
leaving 23-28 for integration + multiple Kaggle submissions + iteration. Tight
but feasible. JAX rewrite scenario adds 2-4 weeks and would push past deadline.

## 8. Concrete next actions

If the user greenlights this design, the immediate work order is:

1. **Day 1 (today):** start `extract_internal_state` investigation. Read
   kaggle_environments orbit_wars source carefully (env-source agent's report
   covers this). Write a tiny script that runs one episode and dumps the
   internal state at each step to JSON.

2. **Day 1 (parallel):** stub out the `src/orbit_wars/sim/` package skeleton
   (`SimState`, `Action`, empty `Simulator` and `ForwardModelValidator` classes).
   Don't implement step() yet — just get the module importable.

3. **Day 2:** finish scenario extractor. Should produce ≥1000 triples per minute.
   First gate.

Both can be done by the user OR by Claude in parallel agent dispatch.
