# Plan A + C parallel kickoff brief — 2026-05-05

**Status:** kickoff design, locked via brainstorm 2026-05-05.
**Companion doc:** `mcts_forward_model_design.md` (the Path C master spec).
**Scope:** decisions and design needed to start Path A (4P tuner retool) and
Path C Day 3-5 (minimal simulator) as parallel workstreams.

This brief does NOT supersede `mcts_forward_model_design.md` for Path C; it
refines its Day 3-5 section with the agreed dev workflow and adds the new
Path A retool design that the master doc doesn't cover.

## 0. Why this exists

Per memory + CLAUDE.md, the Modal CMA-ES tuner is **2P-only** and the recent
2P↔4P spot-check showed rankings DIVERGE between the two game modes (bestv2:
best in 2P at 64% wr, worst in 4P at 20%). A 4P-retool of the tuner is
days, not weeks, and tests whether Path A still has runway *before* the
50-day deadline gets fully consumed by Path C's 22-27 day forward-model
build. Running both in parallel — A as a fire-and-forget Modal sweep, C as
local dev — keeps both bets live.

## 1. Decisions locked in brainstorm

| Decision | Choice | Rationale |
|---|---|---|
| Mode | A + C truly in parallel | A is cloud-side (fire-and-forget), C is local dev. No resource contention. |
| Sequence | A first, then C | Day 1: retool + launch sweep; Day 2-N: C dev while sweep bakes. |
| Path A fitness | Graduated placement (1st=+1, 2nd=+1/3, 3rd=−1/3, 4th=−1) | Denser signal than binary (~25% expected for symmetric); plausibly better Kaggle-Elo correlation. Risk: rewards "lose 2nd gracefully" — accepted. |
| Path A games-per-eval | **N = 33** | SE of mean ≈ 0.13 → can differentiate true graduated-fitness deltas of ~0.26 (2σ). |
| Path A opponent field | 3 archive samples (pure rolling-archive co-evolution, matching Path G) | Maintains co-evolution pressure. Fall back to `starter` for empty slots when archive size <3 early in evolution. |
| Path C dev workflow | Per-phase property tests + validator integration check | Property tests give fast local signal during phase dev; validator's match-rate is the gate. |
| Path C scope (Days 3-5) | Phases 3 (production), 6 (combat), 2 (apply actions); interim Phase 4 stub via `world._build_arrival_ledger`. Skip rotation, comets. | Per master design doc Section 4 build order. |

## 2. Path A — 4P tuner retool design

### 2.1 Game shape

Each fitness eval runs `N = 33` games. Each game is a 4P FFA:

```
players = [candidate_config, archive_sample_a, archive_sample_b, archive_sample_c]
```

Archive samples drawn from the Path G rolling archive. When archive size <3
(early generations), fill remaining slots with `starter`.

### 2.2 Fitness

Per game:
1. Compute each player's final asset count = `sum(planet.ships for planet in owned) + sum(fleet.ships for fleet in owned-in-flight)` per env L687-693.
2. Sort the 4 players by final asset count descending.
3. Score by rank: `[+1, +1/3, −1/3, −1][rank]`.
4. Ties at any rank: average the tied scores. (e.g., tied at ranks 2-3 →
   both get `(1/3 + −1/3)/2 = 0`. Three-way tie at 2-3-4 → all get
   `(1/3 + −1/3 + −1)/3 = −1/3`.)

Fitness = mean of per-game scores across the 33 games. Range: [−1, +1].

### 2.3 Cost guard

- 4P games run ~4× the agent-call work of 2P; Modal parallelizes per game.
- Function timeout: 120min (already in tuner, do not regress per memory).
- `evaluate_fitness.starmap(args, return_exceptions=True)` → map exceptions
  to `DISQUALIFIED_FITNESS` so CMA-ES treats failed games as bad
  candidates and continues. Already in code (`src/tools/modal_tuner.py`),
  do not regress per memory.
- Modal cost-meter overestimates 4-5× per memory; defer to dashboard.
  Budget envelope: $60 loaded; user willing to top up if results justify.

### 2.4 Anti-regression checklist (must preserve from current tuner)

1. Save robust-BEST = best-from-max-archive-size-seen generation (NOT
   best-ever-fitness). Best-ever is biased toward early/warmup gens.
2. Resilient `starmap(..., return_exceptions=True)` per above.
3. Don't introduce a new RNG path; the tuner already uses Modal-side
   seeding.

### 2.5 Done criteria

- Sweep completes (or hits population/generation cap) without crashing.
- BEST config bundled into a submission tarball per the CLAUDE.md
  "Submitting CMA-ES-tuned configs" pattern.
- Submitted to Kaggle ladder.
- Wait 4-6 hours for ladder μ to drift-resolve (per CLAUDE.md ladder note).
- Single μ reading recorded vs. current ~700μ baseline.

## 3. Path C — Day 3-5 implementation plan

Refines `mcts_forward_model_design.md` Section 4 (Day 3-5: Minimal Simulator).

### 3.1 Implementation order (smallest blast-radius first)

1. **`validator.validate()`** lands first — without measurement, no gate.
   - Implements `state_diff(actual: SimState, expected: SimState, pos_tol=0.1, ship_tol=0) -> dict`.
   - Returns categorized mismatches: `ownership-flip`, `ship-count-off`,
     `fleet-position-drift`, `fleet-count-mismatch`, `comet-related`, `step-mismatch`.
   - `validate()` returns `ValidationReport` with category counts so the
     "fix the most-frequent category, re-run" loop is mechanical.
2. **Phase 3 (production)** — trivial. Smoke-tests that validator works end-to-end.
3. **Phase 6 (combat)** — port from `world.resolve_arrival_event`.
4. **Phase 2 (apply actions, spawn half)** — `validate_move` already
   exists; spawn accepted launches as new `SimFleet` with `id =
   state.next_fleet_id`, then increment.
5. **Phase 4 interim stub** — borrow `world._build_arrival_ledger` for
   STATIC-planet projections only. Each accepted fleet teleports to
   ETA-completion; combat aggregator gets fed at the right turn. Real
   Phase 4 (sun + planet collisions, straight-line motion) lands Day 5-7.

### 3.2 Per-phase property tests (hybrid approach)

**Phase 3 (production):**
- For random owned planets, ships-after-step = ships-before + production.
- Neutral planets (`owner == -1`) never gain ships.

**Phase 6 (combat) — most fragile, most tests:**
- Two equal arriving fleets → top-2 cancel, 0 survivors, planet undamaged.
- Top-1 strictly beats top-2 → survivor = top1 − top2, then fights garrison.
- Same-owner arrivals merge into one entry before the top-2 sort.
- Tie at top with garrison present → garrison untouched, ownership unchanged.
- Single arrival vs. neutral garrison: arrival ≥ garrison → capture (ownership flip);
  arrival < garrison → garrison reduced by arrival, no flip.
- Hypothesis test: random multi-fleet arrivals, invariant = total ships
  conserved or destroyed monotonically (no spontaneous creation).

**Phase 2 (apply actions):**
- 4 silent-rejection paths matching `validate_move`'s checks (already
  covered by `TestValidateMove` in `tests/test_sim.py`): source missing,
  source not owned by actor, ships ≤ 0, ships > available. Action-shape
  rejections (not a list, wrong length) are at the `Action.from_env_format`
  parsing layer and already covered by `TestAction`.
- Accepted launch: `next_fleet_id` increments by 1; new SimFleet appended;
  source planet ships reduced by `action.ships`.

**Phase 4 stub:**
- Filtered scenarios only have static planets; each in-flight fleet's
  arrival turn matches `world._build_arrival_ledger`'s prediction.

### 3.3 Scenario filter for the 80% gate

Filter `collect_scenarios()` output to triples where ALL hold:
- `state_t.comet_groups == []` (no comets present)
- All `state_t.planets` are static: `orbital_radius + radius >= ROTATION_RADIUS_LIMIT`
  (same condition env L572 uses to skip rotation)
- `state_t.step` not in `COMET_SPAWN_STEPS`
- `state_t.step + 1` not in `COMET_SPAWN_STEPS`
- `state_t.config.num_agents == 2` (2P only for Day 3-5)

If filter yields <500 triples from a 10-seed × 3-opponent sweep, expand
seeds before retrying — the gate is statistical and needs sample size.

### 3.4 Done criteria

- All per-phase property tests pass (`uv run pytest -q tests/test_sim*.py`).
- `validator.validate()` reports ≥80% match rate on the filtered scenario
  set (per master design doc Section 4 gate).
- Mismatch categorization printed for the ≤20% that didn't match — feeds
  Day 5-7 work.

## 4. Coordination & decision points

| Trigger | Action |
|---|---|
| Path A sweep completes + ladder μ ≥ +50 over baseline (~700) | A still has runway. Keep iterating A before next big A change. C continues at reduced priority. |
| Path A sweep completes + ladder μ within ±50 of baseline | A saturated for real. C is the bet; commit fully. |
| Path A sweep completes + ladder μ ≥ +100 over baseline | A may have more legs (4P-aware features worth exploring). Consider parking C for one more A iteration. |
| Path C Day 3-5 gate fails (<80% match) after one debug day | Surface findings to `docs/iteration_logs/<date>/sim_d3-5_debug.md`. Per master doc, hard-kill of C only at Day 14, but use this signal to question whether to keep building. |
| Path C Day 3-5 gate passes (≥80%) | Continue per master doc Days 5-7 (real fleet movement + sun/planet collisions). |

## 5. Out of scope (deliberately)

- The MCTS algorithm itself — still requires its own design doc once the
  forward-model fidelity gate (Day 14 in master doc) passes.
- Numba/JAX perf work — Days 14-16 in master doc, only after fidelity gate.
- 4P opponent-modeling for MCTS — master doc Section 5 risk #6 flags this
  as research-hard. Becomes acute *only* if the simulator passes Day 14.
- Path B (RL) — referenced as a fallback in master doc but not designed.

## 6. Open items (acknowledged, not blocking kickoff)

- **Game-time per 4P eval is unmeasured.** N=33 games × population_size ×
  generations on Modal — total wall-clock and dollars unknown until first
  sweep runs. Watch the first generation's runtime; abort if absurd.
- **Combined index hygiene.** Per CLAUDE.md, `git commit` sweeps the
  staged index. Always `git status -s` immediately before any commit
  during this work; never use `git add -A`.
- **CMA-ES σ collapse risk.** If σ collapses too fast in early gens
  (overconfident on noisy 4P signal), bump N from 33 to ~64. No
  pre-commitment.

## 7. References

- Master Path C design: `docs/research_documents/mcts_forward_model_design.md`
- Existing tuner: `src/tools/modal_tuner.py` (already has resilient starmap + robust-BEST save)
- Existing sim scaffold: `src/orbit_wars/sim/` (state, action, validator with extract/inject; simulator stubs)
- Existing tests: `tests/test_sim.py`
- Env source: `.venv/lib/python3.13/site-packages/kaggle_environments/envs/orbit_wars/orbit_wars.py`
- Spot-check that surfaced 2P↔4P divergence: `docs/research_documents/spot_checks/2026-05-05T04-11-41Z/`
