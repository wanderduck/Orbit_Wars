# CMA-ES Tuning Framework — Design Spec

**Date:** 2026-05-02 (revised: Modal-from-day-1 architecture; sequential-local MVP no longer the path)
**Phase:** 3 (post-Phase-2 wrap; first Phase 3 deliverable)
**Status:** Awaiting user review before execution
**Predecessors:**
- `docs/research_documents/competition_codebases/synthesis.md` — recommendation #1 in the RL-with-heuristics synthesis was "black-box hyperparameter search over `HeuristicConfig` via CMA-ES."
- `docs/research_documents/phase2_results.md` — Phase 2 surfaced the structural bottleneck (single-opponent saturation, env's hidden random-state consumption invalidating cross-script comparisons) that motivated pivoting to automated multi-opponent tuning.

## Goal

Build the first **automated mechanism for tuning v1.5G's `HeuristicConfig` against measurable fitness**. Replaces the current "hand-pick one or two params, write a one-off A/B script" workflow with a CMA-ES loop that varies all numeric config fields, evaluates each candidate against a fixed multi-opponent panel, and converges toward configurations that beat the current v1.5G baseline.

The framework's scope is **MVP-with-cloud-parallelism**: get from "CMA-ES proposes 50 candidates" to "50 fitness scores back" in minutes (not hours) by fanning out per-candidate evaluations to parallel Modal containers. Sequential local execution would take a full day per sweep — unacceptable for iteration on fitness function and parameter space. Modal-from-day-1 cuts wall-clock to ~2-3 hours per default-quality sweep, at a cost of ~$50-55 per sweep (see Compute budget section for the math). The user's $60 credit funds ~1 default-quality sweep OR ~10+ iteration-quality sweeps — enough to validate the framework and converge on a useful config. Deliberately out-of-scope-for-MVP items (resumability, Pareto multi-objective, full rolling-archive co-evolution) have explicit upgrade paths but are deferred.

## Inputs

- `HeuristicConfig` dataclass at `src/orbit_wars/heuristic/config.py` — 48 numeric fields (verified by `dataclasses.fields` introspection), 2 booleans.
- v1.5G agent at `src/main.py` / `src/orbit_wars/heuristic/strategy.py:agent` — accepts a `HeuristicConfig` argument so candidate configs can be swapped at call time.
- Local sparring partners in `src/orbit_wars/opponents/`:
  - `peer_mdmahfuzsumon` (Phase 2 Step 1, ranked 498 / 796.8 μ at port time).
  - `aggressive_swarm`, `defensive_turtle` (existing weaker locals).
- `kaggle_environments.make("orbit_wars")` — env, ~3 sec/game wall-clock.
- `cma` Python library — added to `pyproject.toml` dependencies (existing project uses scipy, so adding cma is a small dep addition).
- `modal` SDK (>=1.4.2, already in `pyproject.toml`) and active Modal account with the user's existing $60 credit. One-time setup: `uv run modal token new`. Examples in `src/modal_examples/` show the patterns we'll use (`.starmap()` from local entrypoint dispatching to a single `@app.function`, image build via `debian_slim().uv_pip_install(...).add_local_dir(...)`, plain return values aggregated by the entrypoint).

## Deliverables

1. **`src/tools/modal_tuner.py`** — Modal app file containing **both** the `@app.function evaluate_fitness(cfg_dict, candidate_id, generation)` (runs in cloud containers, popsize-many in parallel) and the `@app.local_entrypoint() main()` that drives the CMA-ES outer loop on the user's machine. Run via `uv run modal run src/tools/modal_tuner.py --generations 30 --popsize 30`. Single-file MVP; later refactoring is fine if needed.
2. **`src/tools/heuristic_tuner_param_space.py`** — `ParamSpace` table mapping each HeuristicConfig field to (lower_bound, upper_bound, [is_int]). Pure-Python module with no Modal/heavy imports so it can be imported from both the local entrypoint and inside Modal containers without ballooning the image.
3. **Per-run output directory** at `docs/research_documents/tuning_runs/<UTC-timestamp>/` (written by the local entrypoint, NOT inside Modal containers):
   - `config.json` — parameter space + run hyperparameters (popsize, num_generations, fitness_weights, opponents used, etc.)
   - `generations.jsonl` — one JSON line per generation: best fitness, mean fitness, stddev, best-so-far config snapshot.
   - `best_config.py` — the highest-fitness HeuristicConfig found, written as importable Python (so the user can `from docs...best_config import BEST as cfg`).
   - `final_report.md` — markdown summary readable cold (best vs baseline margin, per-opponent breakdown, top-5 candidate configs).
4. **Smoke tests** at `tests/test_heuristic_tuner.py` covering:
   - `encode(cfg) → decode → cfg'` round-trips every numeric HeuristicConfig field within tolerance (ints exactly, floats within 1e-6).
   - `ParamSpace` table covers every numeric HeuristicConfig field (fail-loud check via `dataclasses.fields` introspection).
   - **Local-only `evaluate_fitness` smoke** — same function body the Modal container will call, exercised in-process with popsize=2, n_games_per_opponent=2, generations=1. Confirms the inner loop works without needing Modal credit. Modal-end-to-end is a separate manual test (`uv run modal run src/tools/modal_tuner.py --generations 1 --popsize 2 --fitness-games-per-opponent 2`) — not in pytest because it costs real money.

## Architecture

### CMA-ES loop (local entrypoint)

```
LOCAL ENTRYPOINT (runs on user's machine):

1. Initialize:
   - x0 = encode(HeuristicConfig.default()) — start from v1.5G baseline
   - sigma0 = 0.25 × (upper - lower) per dim (Hansen's rule; "25% of range" initial exploration)
   - popsize = 30 (overrides cma's default of ~15 — Hansen recommends 30-50 for noisy fitness)
   - es = cma.CMAEvolutionStrategy(x0, sigma0, {'popsize': popsize, 'bounds': [lower, upper], 'integer_variables': INT_DIMS})

2. For each generation:
   a. candidates = es.ask()  # list of popsize param vectors
   b. args = [(decode(x).__dict__, i, gen) for i, x in enumerate(candidates)]
   c. results = list(evaluate_fitness.starmap(args))  # PARALLEL across Modal containers
   d. fitnesses = [r['fitness'] for r in results]
   e. es.tell(candidates, [-f for f in fitnesses])  # CMA-ES minimizes; we maximize, hence negation
   f. log generation metadata (best, mean, stddev, per-opponent breakdown) to generations.jsonl
   g. if best_so_far updates → write best_config.py

3. After N generations or convergence:
   - Write final_report.md
   - Print best config + margin vs baseline
```

### Modal function (per-candidate fitness, runs in cloud container)

```python
@app.function(
    image=tuner_image,        # debian_slim + cma + scipy + numpy + kaggle_environments + src/
    cpu=2.0,                  # 2 physical cores per container
    memory=4096,              # 4 GiB
    timeout=20 * MINUTES,     # generous; one candidate should be ~4 min wall-clock
)
def evaluate_fitness(cfg_dict: dict, candidate_id: int, generation: int) -> dict:
    """One candidate → one fitness score. Runs sanity gate, then fitness games.

    Container is fresh — random state is uncontaminated. We seed once at top.
    """
    import random
    random.seed(GLOBAL_TUNER_SEED)  # deterministic per-container
    cfg = HeuristicConfig(**cfg_dict)
    # Phase 1: sanity gate (cheap; early-exit if disqualified)
    # Phase 2: fitness games vs v1.5G + peer
    return {
        'candidate_id': candidate_id,
        'generation': generation,
        'sanity_pass': bool,
        'fitness': float,        # combined score, or large negative if disqualified
        'per_opp': {'v15g_stock': margin, 'peer_mdmahfuzsumon': margin},
        'sanity_winrates': {'aggressive_swarm': float, 'defensive_turtle': float},
        'wall_clock_seconds': float,
    }
```

The local entrypoint calls `.starmap(args_list)` to dispatch all `popsize` candidates simultaneously to Modal. Each call lands in its own container with its own fresh Python process; results stream back as containers finish.

### Fitness function

```python
def evaluate_fitness(cfg: HeuristicConfig) -> float:
    # Phase 1: sanity gate (cheap)
    for opp in [aggressive_swarm, defensive_turtle]:
        wins, losses = run_games(cfg, opp, n=10)
        if wins / (wins + losses) < 0.91:  # locked in at 91% per brainstorm
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

Per CLAUDE.md (Phase 2 lesson): the env consumes Python's global random state, so within a single Python process, identical configs on identical env seeds can produce different game outcomes depending on stream position. This invalidated cross-script A/B comparisons in Phase 2.

**Modal container isolation solves this for free.** Each `evaluate_fitness.starmap(...)` call lands in its own container with its own fresh Python process and uncontaminated random state:

- `random.seed(GLOBAL_TUNER_SEED)` is called once at the top of `evaluate_fitness` inside every container.
- Every container then runs its sanity + fitness pipeline through the *same* RNG sequence.
- Within a generation, every candidate sees the identical random-state-consumption pattern because the per-container loop structure is identical.
- Across generations, the same property holds — each container is its own clean slate.

This is a non-trivial bonus from going Modal-from-day-1: it not only parallelizes, it eliminates a known correctness pitfall that the local-MVP approach would have had to engineer around.

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

- `popsize`: **50** (Hansen recommends 30-50 for noisy fitness; we go to the upper end of his band). The default formula `4 + floor(3 * ln(N))` for N=48 dims ≈ 15 is far too small for our noisy, single-evaluation-per-candidate landscape.
- `sigma0`: **0.25 × range** per dim (Hansen's rule of thumb). The `cma` library expects sigma0 as a scalar OR a per-dim vector after normalization; we'll normalize bounds to [0, 1] and use sigma0 = 0.25.
- `bounds`: `[normalized_lower=0, normalized_upper=1]` per dim. CMA-ES `BoundPenalty` handler keeps proposals inside the box without hard-clipping (which would distort the mean update).
- `integer_variables`: list of dim indices that should snap to integers post-decode. The `cma` library's built-in handling for integer variables (option `integer_variables` in `CMAOptions`) projects to nearest integer when sampling and rounds when reporting.
- `fitness_games_per_opponent`: **69** (user-chosen for fun number; 60 would be the diminishing-returns floor — 138 total fitness games per candidate gives σ_mean ≈ 0.085 for 0/1 game outcomes, plenty for CMA-ES ranking purposes).
- `generations`: **15-20** (default 15 fits $60 budget at popsize=50; 20 gens recommended if budget allows ~$72 — gives CMA-ES more room to converge on 48-dim problem).
- `ftarget`: `None` (run until generations exhausted).
- `tolfun`: `1e-3` (early stop if best fitness barely changes for several generations).
- **Noise-aware mode** (`'noise_handling'`): consider enabling cma's noise-handling iteration if we observe unstable convergence — re-evaluates promising candidates to reduce noise impact.

## Compute budget

**Per-candidate work (one container, default popsize=50, 69 games/opp):**
- Sanity gate: 20 games × ~3s = ~1 min wall-clock. Early-exit on first opponent < 91% (saves the rest).
- Fitness phase: 138 games (69 × 2 opponents) × ~3s = ~7 min wall-clock.
- Total per candidate (passing sanity): ~8 min; (failing sanity): ~30s-1 min.

**Per generation (popsize=50, fully parallel):**
- All 50 candidates dispatched via `.starmap()` simultaneously.
- Wall-clock = max(container times) ≈ ~8 min for the slowest passing candidate.
- Cold-start overhead: first generation pays ~30s container startup; subsequent generations may reuse warm containers (Modal autoscaling) shrinking this.

**Per default sweep (15 generations, popsize=50, 69 fitness games + 10 sanity games per opponent):**
- Wall-clock: ~15 × 8 min ≈ **2 hours** (vs ~3 days sequential local).
- Modal CPU pricing (current public rate ≈ $0.000131 / CPU-core-second; verify in dashboard before each sweep — pricing changes). 2-core container with 4 GiB RAM ≈ $0.000271 / container-second.
- Per-candidate (passing) cost: 8 min × 60 sec × $0.000271 ≈ $0.130.
- Per-generation cost (50% sanity kill): 25 pass × $0.130 + 25 fail × $0.0163 ≈ $3.66.
- Per-sweep cost: 15 gens × $3.66 ≈ **~$54**.
- The **$60 credit covers exactly 1 default sweep** (with ~$6 buffer for safety).

⚠️ **Cost reality check:** the original brainstorm "$2-5 per sweep" estimate was off by ~10× because it didn't account for popsize × generations × games × seconds × cores × $/sec properly. Concrete budget management:

| Profile | popsize | games/opp | generations | Cost | Wall-clock |
|---|---|---|---|---|---|
| `--smoke` | 4 | 4 | 1 | <$0.10 | ~2 min |
| `--iteration` | 20 | 30 | 15 | ~$8 | ~75 min |
| `--default` (no flag) | 50 | 69 | 15 | ~$54 | ~2 hr |
| `--extended` | 50 | 69 | 30 | ~$108 | ~4 hr |
| `--max-quality` | 100 | 100 | 30 | ~$240 | ~5 hr |

- The `--popsize`, `--generations`, `--fitness-games-per-opponent` CLI flags must be exposed so the user can override individual knobs per run; the profile flags are convenience presets.
- Print estimated cost at run start (popsize × generations × games × seconds × $/sec); refuse to start without `--confirm-cost` flag if estimate exceeds **$20** (the iteration-sweep sentinel).
- After each generation completes, print actual elapsed cost so the user can ctrl-C if they're burning credit faster than expected.

## Output format details

### `config.json`

```json
{
  "run_id": "2026-05-02T19:30:00Z",
  "popsize": 30,
  "num_generations": 30,
  "fitness_weights": {"v15g_stock": 0.6, "peer_mdmahfuzsumon": 0.4},
  "sanity_gate": {"opponents": ["aggressive_swarm", "defensive_turtle"], "min_winrate": 0.91, "n_games": 10},
  "fitness_n_games_per_opponent": 30,
  "estimated_cost_usd": 38.0,
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
    # ... all 48 numeric fields + 2 bools (bools pinned at v1.5G defaults)
)
```

### `final_report.md`

Markdown summary: run config, total time, best fitness vs baseline (with per-opponent breakdown), top-5 configs by fitness, plot-friendly summary of best/mean fitness over generations (text table, no actual plotting in MVP).

## Constraints

- **No edits to existing production code (`src/main.py`, `src/orbit_wars/heuristic/*`)** — the tuner imports `agent`, `HeuristicConfig`, opponents and uses them as-is. Tuning happens entirely in `src/tools/modal_tuner.py` and `src/tools/heuristic_tuner_param_space.py`.
- **No Kaggle submission automation in MVP.** The user takes the best_config.py manually, copies values into HeuristicConfig (or imports), packs a tarball, submits.
- **No mutations to v1.5G's behavior on master.** This whole framework lives in `src/tools/`; importing it has no effect on the production agent.
- **Bools (`reinforce_enabled`, `use_hungarian_offense`) are NOT tuned in MVP.** Pinned at current v1.5G defaults (`reinforce_enabled=True`, `use_hungarian_offense=False`). Categorical handling deferred — could re-run the tuner with different boolean configurations and compare best results.
- **MVP runs on Modal** (CMA-ES outer loop on user's machine; per-candidate fitness eval in cloud containers). One-time setup: `uv run modal token new`. Verify auth + remaining credit in the Modal dashboard before each sweep.
- **Modal image must bake in the source tree** via `.add_local_dir("src", remote_path="/app/src", copy=True)` and install `kaggle_environments`, `cma`, `scipy`, `numpy` via `.uv_pip_install(...)`. Container `PYTHONPATH` (or `sys.path.insert`) must include `/app/src` so `from orbit_wars.heuristic.config import HeuristicConfig` and `from orbit_wars.opponents.peer_mdmahfuzsumon import agent` work inside `evaluate_fitness`.
- **HeuristicConfig serializes to Modal as a plain dict.** Local entrypoint passes `decode(x).__dict__`; container reconstructs via `HeuristicConfig(**cfg_dict)`. Modal pickles arguments natively and dataclasses serialize fine, but explicit dict avoids pickle-version edge cases.
- **No Modal Volume needed for MVP.** Each `evaluate_fitness` call returns a JSON-serializable result dict; the local entrypoint aggregates and writes per-generation results to `docs/research_documents/tuning_runs/<timestamp>/`. Volume only needed when we add resumability across runs (Phase 3.5+).
- **`cma` and `modal` both in `pyproject.toml`** (modal already present at >=1.4.2; cma to be added) and `uv.lock` updated via `uv sync`.

## Out of scope (deferred to Phase 3.5+ or later)

- **Resumability.** If a sweep crashes mid-run, restart from scratch. The per-generation JSONL and best_config.py are preserved each generation, so we don't lose ALL data on crash, but the CMA-ES internal state (covariance matrix, sigma) isn't checkpointed. Adding it requires writing `es.pickle()` to a Modal Volume after each `es.tell()` — straightforward but not in MVP.
- **Pareto multi-objective.** Single scalar fitness in MVP. If/when we want to optimize for "best vs v15g AND best vs peer" as separate dimensions, would need pyMoo or similar.
- **Rolling-archive co-evolution / Phase 3.5.** Fitness function ALREADY takes a list of opponents — adding archive members later is `opponents.append(best_so_far)` every K generations. The architecture is built to support this; it's just not enabled in MVP.
- **Auto-tuning of CMA-ES hyperparameters** (popsize, sigma0). The library has its own self-adaptation for sigma; popsize is fixed at user-chosen value via CLI flag. If we want to sweep the sweep itself, that's much later.
- **Tuning the bools (`reinforce_enabled`, `use_hungarian_offense`).** Could be done by running the framework twice with each boolean configuration and comparing best fitnesses.
- **Multi-machine distributed runs.** Modal handles parallelism within a generation; multiple concurrent sweeps (e.g., on different opponent panels) would be future-future.
- **Modal Volume for cross-sweep state.** No volume in MVP — every sweep starts fresh. Volume gets added only when we want resumability or when sharing intermediate state across sweeps (e.g., warm-start CMA-ES from previous sweep's best).
- **Auto-submit best config to Kaggle.** Local-entrypoint side could in theory call `kaggle competitions submit ...` after writing best_config.py, but this is risky (uses limited daily submission slots automatically). User stays in the loop.

## Done state

- `src/tools/modal_tuner.py` and `src/tools/heuristic_tuner_param_space.py` exist and pass the local-only `evaluate_fitness` smoke test (`uv run pytest tests/test_heuristic_tuner.py`).
- `cma` is in `pyproject.toml` and `uv.lock`; `modal` confirmed at >=1.4.2.
- `uv run modal token new` has been run; `uv run modal app list` works; remaining credit confirmed in dashboard.
- A `--smoke` Modal run completes successfully (`uv run modal run src/tools/modal_tuner.py --smoke`) and writes the expected output files locally. Estimated cost: < $0.10.
- The CLI is documented in `src/tools/modal_tuner.py` module docstring with at least one example invocation for each profile (`--smoke`, `--iteration`, `--default` no-flag, `--extended`, `--max-quality`) AND its estimated cost.
- The user has run at least one **`--iteration`** sweep (~$8 budget) and seen results, BEFORE committing to a `--default` or larger sweep.
- Decisions about whether to ship the best config to ladder are user-driven (not part of this spec — that's a separate Phase 3 step).

## Phase 3.5 upgrade triggers

Concrete signals that should prompt building the next-tier features:

- **Build rolling archive (co-evolution lite)** when: CMA-ES converges and the best config can no longer beat itself in self-play — i.e., we've hit a local-fitness ceiling and need a moving target to escape. Implementation is small: every K generations, append the current best config to the opponent panel and re-weight fitness.
- **Build resumability** when: we have a full-quality sweep we'd actually be sad to lose. Add Modal Volume + `es.pickle()` checkpointing after each `tell()`. (For iteration sweeps at $5-7 each, restart-on-crash is acceptable.)
- **Build Pareto multi-objective** when: we observe the scalar fitness reliably trading off "vs v1.5G" against "vs peer" — i.e., the weighted sum is hiding configs that are great vs one and mediocre vs the other. pymoo's NSGA-II would replace `cma` for the outer loop.
- **Add Modal Volume + cross-sweep state** when: we want to warm-start subsequent sweeps from the previous one's best CMA-ES state, or when we want to share a precomputed opponent panel across multiple parallel sweeps.
