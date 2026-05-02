# CMA-ES Tuning Framework — Design Spec

**Date:** 2026-05-02
**Phase:** 3 (post-Phase-2 wrap; first Phase 3 deliverable)
**Status:** Awaiting user review before execution
**Predecessors:**
- `docs/research_documents/competition_codebases/synthesis.md` — recommendation #1 in the RL-with-heuristics synthesis was "black-box hyperparameter search over `HeuristicConfig` via CMA-ES."
- `docs/research_documents/phase2_results.md` — Phase 2 surfaced the structural bottleneck (single-opponent saturation, env's hidden random-state consumption invalidating cross-script comparisons) that motivated pivoting to automated multi-opponent tuning.

## Goal

Build the first **automated mechanism for tuning v1.5G's `HeuristicConfig` against measurable fitness**. Replaces the current "hand-pick one or two params, write a one-off A/B script" workflow with a CMA-ES loop that varies all numeric config fields, evaluates each candidate against a fixed multi-opponent panel, and converges toward configurations that beat the current v1.5G baseline.

The framework's scope is **minimum viable**: get to "data-driven tuning happens overnight" as fast as possible, observe what works, iterate. Deliberately out-of-scope-for-MVP items (Modal parallelism, resumability, Pareto multi-objective, full co-evolution) have explicit upgrade paths but are deferred.

## Inputs

- `HeuristicConfig` dataclass at `src/orbit_wars/heuristic/config.py` — ~40 numeric fields, 2 booleans.
- v1.5G agent at `src/main.py` / `src/orbit_wars/heuristic/strategy.py:agent` — accepts a `HeuristicConfig` argument so candidate configs can be swapped at call time.
- Local sparring partners in `src/orbit_wars/opponents/`:
  - `peer_mdmahfuzsumon` (Phase 2 Step 1, ranked 498 / 796.8 μ at port time).
  - `aggressive_swarm`, `defensive_turtle` (existing weaker locals).
- `kaggle_environments.make("orbit_wars")` — env, ~3 sec/game wall-clock.
- `cma` Python library — added to `pyproject.toml` dependencies (existing project uses scipy, so adding cma is a small dep addition).

## Deliverables

1. **`src/tools/heuristic_tuner.py`** — Typer CLI entry point (`uv run python -m tools.heuristic_tuner run --generations 30`). Single-file MVP; later refactoring is fine if needed.
2. **`src/tools/heuristic_tuner_param_space.py`** — `ParamSpace` table mapping each HeuristicConfig field to (lower_bound, upper_bound, [is_int]). Importable so tests / future tools can reference.
3. **Per-run output directory** at `docs/research_documents/tuning_runs/<UTC-timestamp>/`:
   - `config.json` — parameter space + run hyperparameters (popsize, num_generations, fitness_weights, opponents used, etc.)
   - `generations.jsonl` — one JSON line per generation: best fitness, mean fitness, stddev, best-so-far config snapshot.
   - `best_config.py` — the highest-fitness HeuristicConfig found, written as importable Python (so the user can `from docs...best_config import BEST as cfg`).
   - `final_report.md` — markdown summary readable cold (best vs baseline margin, per-opponent breakdown, top-5 candidate configs).
4. **Smoke tests** at `tests/test_heuristic_tuner.py` covering:
   - `encode(cfg) → decode → cfg'` round-trips every numeric HeuristicConfig field within tolerance (ints exactly, floats within 1e-6).
   - `ParamSpace` table covers every numeric HeuristicConfig field (fail-loud check via `dataclasses.fields` introspection).
   - Tuner runs at least 1 generation end-to-end without crashing using a tiny budget (popsize=4, n_games_per_opponent=2, generations=1) and produces all expected output files.

## Architecture

### CMA-ES loop

```
1. Initialize:
   - x0 = encode(HeuristicConfig.default()) — start from v1.5G baseline
   - sigma0 = 0.3 (CMA-ES initial step size, in normalized parameter space)
   - es = cma.CMAEvolutionStrategy(x0, sigma0, {'popsize': 15, 'bounds': [lower, upper]})

2. For each generation:
   a. candidates = es.ask()  # list of N param vectors
   b. fitnesses = [evaluate_fitness(decode(x)) for x in candidates]
   c. es.tell(candidates, [-f for f in fitnesses])  # CMA-ES minimizes; we maximize, hence negation
   d. log generation metadata to generations.jsonl
   e. if best_so_far updates → write best_config.py

3. After N generations or convergence:
   - Write final_report.md
   - Print best config + margin vs baseline
```

### Fitness function

```python
def evaluate_fitness(cfg: HeuristicConfig) -> float:
    # Phase 1: sanity gate (cheap)
    for opp in [aggressive_swarm, defensive_turtle]:
        wins, losses = run_games(cfg, opp, n=10)
        if wins / (wins + losses) < 0.90:
            return -1e9  # disqualify; don't waste compute on Phase 2

    # Phase 2: fitness
    margin_v15g = avg_reward_margin(cfg, v15g_stock_agent, n=30)
    margin_peer = avg_reward_margin(cfg, peer_mdmahfuzsumon_agent, n=30)
    return 0.6 * margin_v15g + 0.4 * margin_peer
```

`avg_reward_margin(cfg, opponent, n)`:
- Run `n` games (env seeds 0..n-1, deterministic per call) with `cfg`-configured agent vs `opponent`.
- For each game: margin = `final.r0 - final.r1` (typically -1, 0, or +1 in this env, but could be float).
- Return mean across games.

`v15g_stock_agent` is captured ONCE at framework init via `BASELINE_AGENT = make_v15g_with_cfg(HeuristicConfig.default())`. It does NOT update as candidates improve — it stays as the immortal baseline.

### Random-state-position handling

Per CLAUDE.md "be critical" notes (Phase 2 lesson): the env consumes Python's global random state, so cross-call winrates differ even with identical config + seed.

**Mitigation:** for fairness within a generation, all candidates evaluate against the same random-state-position sequence:

```python
def evaluate_fitness(cfg, generation_seed_offset):
    # Each candidate in the generation uses the same env seed range.
    # random.seed(SEED) is called ONCE before the generation loop, NOT per candidate.
    # Within the candidate's evaluation, sequential seeds 0..n-1 of fitness games
    # all consume from the same RNG state — but every candidate sees the same
    # consumption pattern because the loop structure is identical.
```

Cross-generation comparison is still imprecise (different generations may not be perfectly comparable in absolute fitness), but **within-generation** ranking — which is what CMA-ES uses to update its covariance matrix — is fair.

### ParamSpace

A table mapping each tunable HeuristicConfig field to its (lower, upper, is_int) bounds:

```python
PARAM_SPACE: dict[str, tuple[float, float, bool]] = {
    # Send margins
    "safety_margin": (0, 5, True),
    "home_reserve": (0, 10, True),
    "min_launch": (5, 50, True),
    "defense_buffer": (0, 8, True),
    # Value multipliers
    "static_neutral_value_mult": (0.5, 3.0, False),
    "static_hostile_value_mult": (0.5, 3.0, False),
    # ... etc.
}
```

The table covers every numeric field of `HeuristicConfig` except the two booleans (`reinforce_enabled`, `use_hungarian_offense`) which are pinned at current defaults per the constraints section. The full table is enumerated in `src/tools/heuristic_tuner_param_space.py` (deliverable #2). Implementation derives the field list from `dataclasses.fields(HeuristicConfig)` and asserts every numeric field has an entry — so adding a new HeuristicConfig field will fail-loudly until its bound is also added to the table.

Bounds chosen for sanity (e.g., min_launch must be ≥1; multipliers can't be negative). Initial table is hand-written; future iterations can refine based on what CMA-ES converges toward.

`encode(cfg) -> np.ndarray` and `decode(np.ndarray) -> HeuristicConfig` round-trip the config through the parameter vector. Integer fields are decoded via `int(round(x))` after CMA-ES proposes a continuous value.

### CMA-ES hyperparameters (defaults)

- `popsize`: `cma`-default formula = `4 + floor(3 * ln(N))`. For N=40: ≈ 15.
- `sigma0`: `0.3` (in normalized parameter space — i.e., 30% of the bounds range as initial exploration).
- `bounds`: `[normalized_lower, normalized_upper]` per dim.
- `ftarget`: `None` (run until generations exhausted).
- `tolfun`: `1e-3` (early stop if best fitness barely changes for several generations).

## Compute budget

- Per candidate fitness eval: ~3.5 min (60 fitness games + 20 sanity games at ~3s each).
- Per generation: 15 candidates × 3.5 min ≈ 53 min.
- Per full sweep (30 generations): ~26 hours wall-clock sequentially.

This is the upper bound assuming all candidates pass the sanity gate. Realistic: many will fail the gate and skip the expensive fitness phase, so generations are typically faster.

**Modal upgrade path (Phase 3.5+):** if 26 hours per sweep proves too slow for iteration, port `evaluate_fitness` to Modal. The CMA-ES outer loop runs locally; each generation's `[evaluate_fitness(c) for c in candidates]` becomes parallel Modal calls. Estimated 1 day of dev to wire Modal up; uses the existing $60 credit.

## Output format details

### `config.json`

```json
{
  "run_id": "2026-05-02T19:30:00Z",
  "popsize": 15,
  "num_generations": 30,
  "fitness_weights": {"v15g_stock": 0.6, "peer_mdmahfuzsumon": 0.4},
  "sanity_gate": {"opponents": ["aggressive_swarm", "defensive_turtle"], "min_winrate": 0.90, "n_games": 10},
  "fitness_n_games_per_opponent": 30,
  "param_space": {...},
  "baseline_config": {...},
  "cma_options": {...},
  "started_at": "...",
  "completed_at": "..."
}
```

### `generations.jsonl`

One JSON object per line, per generation:

```json
{"gen": 0, "best_fitness": -0.32, "mean_fitness": -0.55, "fitness_stddev": 0.18, "best_candidate": {...full HeuristicConfig...}, "per_opponent_breakdown": {"v15g_stock": -0.30, "peer": -0.35}, "n_disqualified_by_sanity": 3, "wall_clock_seconds": 2870}
```

### `best_config.py`

```python
"""Best config from tuning run 2026-05-02T19:30:00Z.
Best fitness: 0.42 (vs baseline 0.0). Best vs v15g_stock: 0.55. Best vs peer: 0.22.
"""
from orbit_wars.heuristic.config import HeuristicConfig

BEST = HeuristicConfig(
    safety_margin=2,
    home_reserve=3,
    # ... all 40 fields
)
```

### `final_report.md`

Markdown summary: run config, total time, best fitness vs baseline (with per-opponent breakdown), top-5 configs by fitness, plot-friendly summary of best/mean fitness over generations (text table, no actual plotting in MVP).

## Constraints

- **No edits to existing production code (`src/main.py`, `src/orbit_wars/heuristic/*`)** — the tuner imports `agent`, `HeuristicConfig`, opponents and uses them as-is. Tuning happens entirely in `src/tools/heuristic_tuner*.py`.
- **No Kaggle submission automation in MVP.** The user takes the best_config.py manually, copies values into HeuristicConfig (or imports), packs a tarball, submits.
- **No mutations to v1.5G's behavior on master.** This whole framework lives in `src/tools/`; importing it has no effect on the production agent.
- **Bools (`reinforce_enabled`, `use_hungarian_offense`) are NOT tuned in MVP.** Pinned at current defaults (True, False respectively). Categorical handling deferred — could re-run the tuner with different boolean configurations and compare best results.
- **MVP runs locally** on the user's machine. Modal integration is an explicit Phase 3.5 extension.
- **`cma` library** added to `pyproject.toml` dependencies and `uv.lock` updated via `uv sync`.

## Out of scope (deferred to Phase 3.5+ or later)

- **Modal parallelism.** Easy upgrade path: replace the per-generation fitness loop with parallel Modal calls. Architecture supports it (each candidate eval is independent).
- **Resumability.** If a run crashes mid-sweep, restart from scratch. The per-generation JSONL and best_config.py are preserved each generation, so we don't lose ALL data on crash, but the CMA-ES internal state isn't checkpointed.
- **Pareto multi-objective.** Single scalar fitness in MVP. If/when we want to optimize for "best vs v15g AND best vs peer" as separate dimensions, would need pyMoo or similar.
- **Rolling-archive co-evolution / Phase 3.5.** Fitness function ALREADY takes a list of opponents — adding archive members later is `opponents.append(best_so_far)` every K generations. The architecture is built to support this; it's just not enabled in MVP.
- **Auto-tuning of CMA-ES hyperparameters** (popsize, sigma0). The library has its own self-adaptation for sigma; popsize is fixed at the default formula. If we want to sweep the sweep itself, that's much later.
- **Tuning the bools (`reinforce_enabled`, `use_hungarian_offense`).** Could be done by running the framework twice with each boolean configuration and comparing best fitnesses.
- **Multi-machine distributed runs.** Modal handles parallelism within a generation; multiple concurrent sweeps (e.g., on different opponent panels) would be future-future.

## Done state

- `src/tools/heuristic_tuner.py` and `src/tools/heuristic_tuner_param_space.py` exist and pass the smoke test.
- `cma` is in `pyproject.toml` and `uv.lock`.
- A 1-generation smoke run completes successfully and writes the expected output files.
- The CLI is documented in `src/tools/heuristic_tuner.py` module docstring with at least one example invocation.
- The user has run at least one full overnight sweep and has a `best_config.py` to look at.
- Decisions about whether to ship the best config to ladder are user-driven (not part of this spec — that's a separate Phase 3 step).

## Phase 3.5 upgrade triggers

Concrete signals that should prompt building the next-tier features:

- **Build Modal parallelism (option B from earlier brainstorm)** when: a single 30-generation sweep takes > 24 hours wall-clock AND we want to iterate on fitness function / parameter space; OR when we want to run multiple independent sweeps (different opponent panels, different param subsets) concurrently.
- **Build rolling archive (co-evolution lite)** when: CMA-ES converges and the best config can no longer beat itself in self-play — i.e., we've hit a local-fitness ceiling and need a moving target to escape.
- **Build resumability** when: we have a sweep we'd actually be sad to lose. (For experimental sweeps, restart-on-crash is acceptable.)
