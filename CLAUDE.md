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

# Submit (run from the directory holding main.py — see submission packaging below)
kaggle competitions submit orbit-wars -f main.py -m "<message>"
kaggle competitions submissions orbit-wars
```

There is no test suite, linter, or formatter configured. If you add one, document it here.

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

- **`obs` may be a dict OR a namespace.** The current code handles both via `obs.get(k, default) if isinstance(obs, dict) else obs.k`. Preserve that pattern in new code.
- **Comets are aliased into `obs.planets`.** Filter with `obs.comet_planet_ids` when iterating "real" planets — comets disappear when they leave the board and take their garrisons with them.
- **Planet rotation is deterministic.** `obs.angular_velocity` plus `obs.initial_planets` lets you predict any orbiting planet's future position; don't aim at *current* coordinates of a moving planet from far away.
- **Fleet speed scales with fleet size** (`speed = 1 + (max-1) * (log(ships)/log(1000))^1.5`). Splitting a large fleet into many tiny fleets dramatically slows them down.
- The named tuples `Planet`, `Fleet`, plus `CENTER` and `ROTATION_RADIUS_LIMIT` are exported from `kaggle_environments.envs.orbit_wars.orbit_wars`.

The current `agent` is a "nearest-planet sniper" baseline (capture closest unowned planet whenever you have `garrison + 1` ships). Treat it as a placeholder — it ignores the sun, comets, planet rotation, fleet collisions in transit, and 4-player dynamics.

## Known gaps / be critical

- **`kaggle_environments` is not declared in `pyproject.toml`.** It is required to run any local game and to be importable by `main.py`. If `uv run python -c "import kaggle_environments"` fails, add it (`uv add kaggle-environments`) before debugging further. Do not silently work around the missing import.
- **`README.md` is explicitly marked as a placeholder.** Don't trust it for current state.
- `data/`, `models/`, `notebooks/` exist but are empty; no data-pipeline conventions have been set yet.

## Repo layout (only the non-obvious bits)

- `src/main.py` — the agent. This is the file that ships.
- `docs/competition_documentation/` — game rules, agent guide, important links. Source of truth for game semantics.
- `images/` — referenced from docs/notebooks; not part of submissions.
- `.cadence/configs/` — empty; reserved (purpose not yet established in this repo).
