# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Single-developer Kaggle competition entry for **Orbit Wars** (https://www.kaggle.com/competitions/orbit-wars), a real-time-strategy simulation tournament. Final submission deadline: **2026-06-23**. There is no production system — every change is in service of producing a stronger `agent(obs)` function for the leaderboard.

Authoritative game rules and observation schema live in `docs/competition_documentation/Orbit_Wars-game_and_agents_overviews.md` and `Orbit_Wars-competition_overview_and_rules.md`. **Read these before changing agent logic** — the rules are sharp-edged (sun collisions destroy fleets, comets share IDs with planets, fleet speed is a logarithmic function of fleet size, combat resolves via "largest vs. second-largest" survivors).

## Toolchain

- **Package manager: `uv`** (uv.lock is committed). Do not `pip install` into the venv.
- Python **3.13** pinned in `pyproject.toml`.
- The pyproject pulls **CUDA 13.0 wheels** (`pytorch-cu130` index, RAPIDS `*-cu12==26.2.*`, `tensorflow[and-cuda]`). Heavy CUDA stack — expect slow first-time `uv sync`.
- `.envrc` prepends NVIDIA `cudnn/lib` and `tensorrt` to `LD_LIBRARY_PATH`. Run `direnv allow` once after cloning, otherwise TF/Torch may not find CUDA libs.

## Commands

```bash
# Install / refresh dependencies
uv sync

# Run anything inside the project venv
uv run python -c "import torch; print(torch.cuda.is_available())"

# Smoke-test the agent locally against the random baseline
uv run python -c "from kaggle_environments import make; env = make('orbit_wars', debug=True); env.run(['src/main.py', 'random']); print([(i, s.reward, s.status) for i, s in enumerate(env.steps[-1])])"

# Self-play (validation episode mirrors what Kaggle runs on submission)
uv run python -c "from kaggle_environments import make; env = make('orbit_wars', debug=True); env.run(['src/main.py']*2)"

# Submit — multi-file agents need the pack tarball, not a bare main.py
uv run python -m tools.cli pack --out submission.tar.gz
kaggle competitions submit orbit-wars -f submission.tar.gz -m "<message>"
kaggle competitions submissions orbit-wars

# Track ladder games for a specific submission (sample-size signal)
uv run kaggle competitions episodes <subId> -v
```

Run tests: `uv run pytest -q` (37 tests; geometry/rotation/world combat resolution; uses `hypothesis` for property tests). Mark slow tests with `@pytest.mark.slow` and run via `-m slow`. Lint: `uv run ruff check src tests`. Type-check: `uv run ty check src` (config in `pyproject.toml`).

The Typer CLI: `uv run orbit-play {play,ladder,replay,pack,train,eval} --help`. `pack` produces a submission tarball with a G4 smoke test built in.

## Submission packaging — important

Kaggle requires **`main.py` at the bundle root**. The agent currently lives at `src/main.py`. For multi-file agents, bundle into a tar.gz with `main.py` at the root:

```bash
tar -czf submission.tar.gz -C src main.py <other files>
kaggle competitions submit orbit-wars -f submission.tar.gz -m "<message>"
```

When you split the agent into helper modules, keep imports relative-flat (no package layout) — Kaggle unpacks the tarball into a single working directory.

**Per competition rules (Section 12):** the agent must not perform network I/O during episode evaluation. Bundle any model weights into the tarball.

## Agent architecture

The submission entry point is `src/main.py:agent(obs)`. It is **stateless** by contract — Kaggle calls it once per turn with up to 1 second wall-clock (`actTimeout=1`). Persisting state across turns requires a module-level cache; remember the same agent function is also used for self-play validation, so any cache must be keyed by `obs.player` or reset when a new episode begins.

Critical observation/action quirks:

- **`obs` may be a dict OR a Struct.** Use `ObservationView.from_raw(obs)` (in `orbit_wars.state`) or the dual-mode pattern. Preserve in new code.
- **`agent(obs, config=None)` signature trap.** `kaggle_environments.env.run` passes its env-config Struct as the second positional arg. If you write `cfg = config or DEFAULT`, the truthy Struct overrides DEFAULT and `cfg.<attr>` raises AttributeError, gets caught by the boundary `try/except`, and the agent returns `[]` every turn for the entire episode — silently. **Always guard with `isinstance(config, HeuristicConfig)`.** This bug cost hours in v1.0; never repeat it.
- **Comets are aliased into `obs.planets`.** Filter with `obs.comet_planet_ids` when iterating "real" planets. Comets vanish when they leave the board (taking garrisoned ships with them) — `aim_with_prediction` caps ETA at `len(comet_path) - comet_path_index`; if you bypass the helper, replicate the cap.
- **`obs.step` is populated by the env** (1-indexed turn). Don't build a module-level counter cache to track step number — the cache pollutes when post-hoc diagnostic re-walks env.steps with `decide_with_decisions`. `ObservationView.from_raw` reads it; just use `view.step`.
- **Planet rotation: rotate from CURRENT position, not `initial_planets`.** At step N obs, the planet has undergone (N−1) rotations from initial. Agents don't know N. `predict_planet_position(target_now, ang_vel, ETA)` is correct; `predict_planet_position(initial, ang_vel, ETA)` is off by N−1 (constant ~1-unit drift per game). Was an off-by-N bug in v1.2.
- **Fleets collide with ANY planet on the path, not just sun and target.** Per E1 / E3: "Collides with any planet (path segment comes within the planet's radius). This triggers combat." Use `path_collision_predicted` in `orbit_wars.world` — walks the trajectory turn-by-turn, predicts each non-target planet's position, returns the first interceptor or None. Static-position checks at launch time are insufficient because moving planets sweep into stationary fleets (env phase 6).
- **Fleet speed scales with fleet size** (`speed = 1 + (max-1) * (log(ships)/log(1000))^1.5`). Splitting a large fleet into many tiny fleets dramatically slows them down. Splitting also costs path-clearance verifications per fleet.
- The named tuples `Planet`, `Fleet`, plus `CENTER` and `ROTATION_RADIUS_LIMIT` are exported from `kaggle_environments.envs.orbit_wars.orbit_wars`.
- **Built-in `starter` opponent only attacks STATIC planets** (`orbital_r + p.radius >= ROTATION_RADIUS_LIMIT`), aim-at-current-position, sends `mp.ships // 2`. No defense, no aim correction. Source: `.venv/lib/python3.13/site-packages/kaggle_environments/envs/orbit_wars/orbit_wars.py:773`. Useful baseline; ~95% v1.5 win rate on 100 seeds — does NOT differentiate Hungarian vs greedy.

The current agent (v1.5G) is a nearest-target sniper plus defense, with WorldModel-backed sizing, intercept aim for orbiting/comet targets, path-clearance, late-game launch filter (skip launches whose ETA exceeds `EPISODE_STEPS - obs.step`), and a `HeuristicConfig` dataclass for tuning. Offense planner is toggleable via `use_hungarian_offense` (default `False` — greedy = v1.4 semantics; `True` = scipy linear_sum_assignment one-to-one matching). Defense is enabled by default (`reinforce_enabled=True`): `find_threats` walks `WorldModel.base_timeline` for forecast ownership flips, `plan_defense` reserves ships from the nearest viable source. Local performance: 100% vs all current sparring partners (20 seeds × 5 opponents). Kaggle ladder: v1.4 settled at ~700 μ; v1.5 (Hungarian + defense) early readings ~600-655 μ; **v1.5G (greedy + defense) is high-variance with recent submissions spanning roughly 650-800 μ — treat ~700 μ as the working median with a ~100 μ noise band per submission.** An earlier reading of ~800 μ that briefly suggested clear improvement has since drifted back down to the ~650-700 range; either the early high was variance / favourable matchmaking, or competition is genuinely strengthening (or both). Per-submission ladder noise is a major factor in any A/B comparison at this μ level.

## Known gaps / be critical

- **README.md is a placeholder** — don't treat it as documentation.
- **Local opponent pool is all-beaten 100%.** `random`, `starter`, `competent_sniper`, `aggressive_swarm`, `defensive_turtle` — none differentiate v1.4 from v1.5 from v1.5G. Self-play also favors v1.5 contradicting Kaggle data. Ground truth for ranking changes lives only on the Kaggle ladder; budget submission slots accordingly (≈3/day).
- **Hungarian vs greedy offense — still unresolved within noise band.** v1.5G (greedy + defense) recent readings span ~650-800 μ; v1.5 (Hungarian + defense) prior readings were ~600-655 μ. With v1.5G's ~100 μ per-submission swing, the apparent gap collapses into the noise floor — the A/B is not actually decided. `use_hungarian_offense=False` remains the working default for v1.5G but should NOT be treated as proven superior. A future controlled re-test (multiple submissions of each variant) would be needed to resolve.
- **No 4-player FFA-aware logic.** Agent treats all non-self planets as targets without considering kingmaker dynamics or alliance-of-convenience patterns.
- **No multi-source coordination.** Each owned planet picks a target independently; no swarm mission (E6 pattern).
- **`uv.lock` pins large CUDA/RAPIDS stack** — `uv sync` is slow (~minutes). The agent itself doesn't need GPU; it's there for the v2+ RL scaffold (currently stubs in `src/orbit_wars/rl/`).
- **Env consumes Python's global random state — cross-script A/B comparisons are INVALID.** Same `configuration={'seed': N}` produces *different* game outcomes depending on what position-in-stream the game runs at, because env internals consume from `random` between turns. Phase 2 Step 4 surfaced this concretely: the same `HeuristicConfig.default()` got 98% in a 2-variant script and 93% in a 4-variant script vs the same opponent on the same env seeds. **Within-script comparisons remain valid** (matched random-stream positions). For any future A/B: run all variants in the same script, alternating per seed. Don't compare winrates across separately-launched scripts.
- **2-variant gates can be misleading; prefer multi-variant ablation.** Step 4's 2-variant gate said "passes" (98% vs 98%, Δ=0). The 4-variant ablation revealed the bundle's pincer toggle was -5% standalone — hidden because the 2-variant comparison happened to show two configs that were equally bad in different ways. When investigating a bundle of N changes, run N+1-variant ablation (control + each toggle individually).

## Diagnostics & debugging

When the agent loses or behaves unexpectedly, **diagnose before fixing**. The tools that exist:

- `uv run python -m tools.diagnostic --seeds 0,1,2,3,4 --out docs/iteration_logs/<v>/diag.json` — instruments the agent, logs every launch with target/ships/eta, then walks env.steps to resolve outcome (`captured`, `still-neutral-at-arrival`, `fleet-destroyed-in-transit`, `enemy-defended`, `arrival-after-episode-end`, etc). Outputs JSON + Markdown summary tables. **Caveat:** `arrival-after-episode-end` means "arrived after the actual episode ended" (often early termination on a win, not turn 500), not "arrived after turn 500". Most short games will report this for late-game launches even if the launch was correct.
- `uv run python -m tools.trace_launch --seed 0 --target-type {static,orbiting,comet}` — picks specific launches and walks env.steps to find the fleet's actual trajectory and where it disappeared. Useful for verifying hypotheses before coding fixes.
- For reproducible tournaments, set `random.seed(42)` ONCE before the seed loop. `random_agent` and env internals consume Python's global random state; per-seed reseeding gives different results than running 10 seeds straight. (env's own seed via `configuration={'seed': N}` is independent.)
- **kaggle_environments quirk**: `env.run` calls agent functions via `inspect.signature` — closures with `*args, **kwargs` get called with NO args because the inspector sees 0 required params. Always use a real function with explicit `obs` parameter.

## Repo layout (only the non-obvious bits)

- `src/main.py` — the agent. This is the file that ships.
- `src/orbit_wars/opponents/` — local sparring partners (`competent_sniper`, `aggressive_swarm`, `defensive_turtle`). All currently beaten 100% by our agent. NOT shipped — for `orbit-play ladder` only.
- `docs/competition_documentation/` — game rules, agent guide, important links. Source of truth for game semantics.
- `images/` — referenced from docs/notebooks; not part of submissions.
- `.cadence/configs/` — empty; reserved (purpose not yet established in this repo).
