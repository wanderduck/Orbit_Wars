---
title: Orbit Wars — Multi-Agent Orchestration & v1 Codebase Design
date: 2026-04-30
status: approved-for-implementation-planning
authors: Wanderduck (user) + Claude Code (orchestrator)
related:
  - ../../../CLAUDE.md
  - ../../competition_documentation/Orbit_Wars-game_and_agents_overviews.md
  - ../../competition_documentation/Orbit_Wars-competition_overview_and_rules.md
  - ../../competition_documentation/Orbit_Wars-important_links.md
---

# Orbit Wars — Multi-Agent Orchestration & v1 Codebase Design

## 0. Purpose

This document specifies (a) a multi-agent orchestration plan for bootstrapping the Orbit Wars Kaggle submission, and (b) the v1 codebase that orchestration will produce. It is the brainstorming output that the `superpowers:writing-plans` skill will turn into an executable implementation plan.

The orchestrator (Claude Code, this session) acts as the 13th agent — Team Lead, Head Orchestrator, Final Editor, Senior Python Developer — coordinating 12 sub-agents across three phases.

## 1. Goals & non-goals

### Goals

1. Produce a **competitive v1 agent** (heuristic, well-engineered) submitted to the Orbit Wars competition within ~1 day of executing this plan.
2. Build the **iteration substrate** (typed game model, fast simulator, RL training scaffold, self-play CLI, tests, packager) such that v2 / v3 / v4 can layer in stronger techniques without re-architecture.
3. Set the user up to plausibly **reach the top of the leaderboard** (top-10 is the stretch goal) by the **2026-06-23** final-submission deadline through iterative improvements rather than one big bet.

### Non-goals (v1 scope discipline)

- v1 does **not** ship an RL-trained agent. RL infrastructure is *built* in v1 but does not gate v1 submission.
- v1 does **not** include 4-player kingmaker logic, endgame ship-counting optimization, or population-based training. Those are v3/v4.
- v1 does **not** add features that aren't required for the heuristic to work, the simulator to mirror Kaggle, or the CLI to package submissions.

### Explicit non-promises (be critical)

- **Top-10 placement is not guaranteed.** It depends on competitor strength, which is unknown. What is high-confidence: the codebase compounds investment well. What is medium-confidence: v2+ surpasses pure-heuristic competitors. Top-10 specifically is low-confidence until we see leaderboard data.

## 2. Operating context

- **User:** solo developer (Wanderduck). Local hardware: RTX 2080 Ti (Turing, sm_75, 11 GB VRAM).
- **Toolchain:** Python 3.13 pinned in `pyproject.toml`; `uv` for dependency management; CUDA 13.0 wheels (PyTorch cu130, RAPIDS 26.2). `kaggle_environments` is **missing** from `pyproject.toml` despite being imported by `src/main.py` — fixing this is task zero of Phase 3.
- **Submission:** `main.py` at the bundle root, single file or tar.gz. 5 submissions/day cap. 1-second per-turn budget (`actTimeout=1`). No network during episode evaluation (Section 12 of competition rules).
- **Source-of-truth docs:** `docs/competition_documentation/*.md` (game rules, agent contract, important links).
- **Date:** Today is 2026-04-30. Final submission deadline 2026-06-23 — ~8 weeks of wall-clock.

## 3. Agent roster (13 total)

### 3.1 Phase 1 — Exploration (9 sub-agents, all parallel)

All Phase 1 agents use `subagent_type: general-purpose` (gives them full tools including Read, WebFetch, Bash). All are instructed to use sequential-thinking MCP and to "think deeply" before producing their report.

| ID | Target | Output file |
|----|--------|-------------|
| **E1** | `docs/competition_documentation/Orbit_Wars-competition_overview_and_rules.md` Section 1 ("Orbit Wars: Kaggle Competition Overview") | `docs/internal/findings/E1-competition-overview.md` |
| **E2** | Same file Section 2 ("Orbit Wars: Kaggle Competition Rules") | `docs/internal/findings/E2-competition-rules.md` |
| **E3** | `docs/competition_documentation/Orbit_Wars-game_and_agents_overviews.md` Section 1 ("Orbit Wars: Game Overview") | `docs/internal/findings/E3-game-overview.md` |
| **E4** | Same file Section 2 ("Orbit Wars: Agents Overview") | `docs/internal/findings/E4-agents-overview.md` |
| **E5** | https://www.kaggle.com/code/bovard/getting-started | `docs/internal/findings/E5-bovard-getting-started.md` |
| **E6** | https://www.kaggle.com/code/pilkwang/orbit-wars-structured-baseline | `docs/internal/findings/E6-pilkwang-structured-baseline.md` |
| **E7** | https://www.kaggle.com/code/kashiwaba/orbit-wars-reinforcement-learning-tutorial | `docs/internal/findings/E7-kashiwaba-rl-tutorial.md` |
| **E8** | https://www.kaggle.com/code/sigmaborov/lb-958-1-orbit-wars-2026-reinforce | `docs/internal/findings/E8-sigmaborov-lb958-reinforce.md` |
| **E9** | https://www.kaggle.com/code/romantamrazov/orbit-star-wars-lb-max-1224 | `docs/internal/findings/E9-romantamrazov-lb1224.md` |

**Notebook fetch protocol (E5–E9):** try `kaggle kernels pull <user>/<slug> --metadata -p <tmp>` first, then read the resulting `.ipynb`. Fall back to WebFetch on the URL only if `kaggle kernels pull` fails. Document which method succeeded.

**Mandatory output schema (every E-agent):**

```markdown
# E<N>: <slug>

## Source
<URL or file:section>

## Fetch method
<kaggle kernels pull | WebFetch | Read>

## Goal
<what this artifact is trying to accomplish>

## Methods
<algorithms, data structures, network architecture if applicable>

## Numerical params / hyperparams
<every constant worth knowing>

## Reusable code patterns
<patterns, idioms, utilities we should adopt — with snippets>

## Reported leaderboard score
<if any; "n/a" otherwise>

## Anything novel worth replicating
<bullet list>

## Direct quotes / code snippets to preserve
<verbatim excerpts>

## Open questions / things I couldn't determine
<bullet list>
```

### 3.2 Phase 2 — Synthesis (orchestrator only, no sub-agents)

Per Approach C (Hybrid), the orchestrator reads all 9 E-reports directly and produces the integrated brief.

**Output:** `docs/internal/findings/00-orbit-wars-synthesis.md` containing:

1. **Rules & Constraints Codex** (from E1+E2): every numeric parameter, every game rule, every submission constraint, every legal restriction. Cross-reference to source.
2. **Game Mechanics & Agent Contract Codex** (from E3+E4): formal state space, action space, dynamics, scoring, agent function signature, observation field reference, named-tuple imports.
3. **Cross-notebook pattern table** (from E5–E9): rows = patterns/techniques, columns = (pilkwang, kashiwaba, sigmaborov, romantamrazov, bovard); cells = "yes/no/variant" with brief notes. Highlights what scored well.
4. **Adoption decisions**: for each pattern, an "adopt / consider for v2 / skip" verdict with reasoning.
5. **3–9 actionable recommendations** for our codebase: concrete, prioritized, mapped to C1/C2/C3.

### 3.3 Phase 3 — Implementation (3 coders + orchestrator, tiered)

| ID | Subagent type | Tier | Owns |
|----|---------------|------|------|
| **C1** | `parseltongue:python-pro` | 1 (parallel with C3-part-1) | Domain model + fast simulator |
| **C3** part-1 | `python3-development:python-cli-architect` | 1 | Toolchain bootstrap (deps, CUDA sanity check, Typer scaffold) |
| **C2** | `parseltongue:python-pro` (with `yzmir-pytorch-engineering:pytorch-code-reviewer` as consultant) | 2 (blocks on C1) | RL training scaffold |
| **C3** part-2 | `python3-development:python-cli-architect` | 2 (blocks on C1) | v1 heuristic agent + remaining CLI + tests + packager |
| **Orchestrator** | n/a | 3 (after all coders) | Integration, code review, submission gate |

**C1 deliverables:**
- `src/orbit_wars/state.py` — typed `Planet`, `Fleet`, `Comet`, `ObservationView` (handles dict-or-namespace obs uniformly).
- `src/orbit_wars/geometry.py` — `dist`, `angle_between`, `sun_segment_intersect(p1, p2, sun_center, sun_radius)`, `intercept_solver(launcher_xy, target_xy, target_velocity, fleet_speed_curve)`.
- `src/orbit_wars/rotation.py` — `predict_planet_position(initial_planet, angular_velocity, steps_ahead) → (x, y)`.
- `src/orbit_wars/sim.py` — Python game simulator that mirrors `kaggle_environments.envs.orbit_wars` semantics for fast RL rollouts. Pure-Python, no Kaggle harness overhead.
- Tests: `tests/test_geometry.py`, `tests/test_rotation.py`, `tests/test_sim_parity.py` (sim matches `kaggle_environments` on N=20 seeded episodes).

**C3 part-1 deliverables (Tier 1):**
- Add to `pyproject.toml`: `kaggle-environments`, `gymnasium`, `pytest`, `pytest-cov`, `ruff`, `mypy` or `ty`, `typer[all]`, `rich`, `hypothesis` (for property tests of geometry); make `modal` an optional dep group (`[project.optional-dependencies] remote = ["modal"]`).
- One-line CUDA sanity check executable as `uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no-gpu')"`. Documents result; if Turing/sm_75 fails on cu130, drop to cu128 wheels (decision documented).
- `src/tools/cli.py` — Typer app with stub commands: `play`, `ladder`, `replay`, `pack`, `train`, `eval`. Each is a stub that prints what it will do.
- Project entry point in `pyproject.toml`: `[project.scripts] orbit-play = "tools.cli:app"`.

**C2 deliverables (Tier 2, blocks on C1):**
- `src/orbit_wars/rl/policy.py` — small actor-critic with set/graph encoder over planets + fleets. Param budget ≤ 1M (CPU inference at 1s/turn must be safe).
- `src/orbit_wars/rl/env.py` — `gymnasium.Env` wrapping `sim.py`. Action space: per-planet `(angle_bucket, ship_fraction_bucket)` heads; angle ∈ 32 buckets, ship-fraction ∈ {0, 1/8, 1/4, 1/2, 3/4, all}; `0` = no launch.
- `src/orbit_wars/rl/train.py` — PPO with self-play league. Opponent pool keyed by TrueSkill rating, matchmaking samples top-k. Checkpointing every N steps. Resume from checkpoint.
- `src/orbit_wars/rl/eval.py` — head-to-head harness (RL vs heuristic, RL vs `random`, RL vs older RL checkpoints). Returns win-rate + score-margin.
- `src/orbit_wars/rl/remote.py` — Modal abstraction. Default `local` mode runs everything in-process; `--remote modal` mode farms rollouts to Modal workers via the `modal-serverless-gpu` skill. Build the abstraction now; flip later if needed.
- Reward: terminal score-difference (sparse) by default. Shaped intermediate rewards (planets captured, ships preserved) gated behind a `--shaped-reward` flag, off by default.
- Eval gate (documented in `eval.py`): an RL checkpoint replaces the heuristic in submission only when it beats the heuristic in 100-episode self-play with **≥60% win rate**.

**C3 part-2 deliverables (Tier 2, blocks on C1):**
- `src/orbit_wars/heuristic/config.py` — `HeuristicConfig` dataclass collecting every tunable weight and threshold (see §7.2 for the list and tentative initial values).
- `src/orbit_wars/heuristic/strategy.py` — top-level `agent(obs)` that `src/main.py` re-exports. **This is what v1 ships.**
- `src/orbit_wars/heuristic/targeting.py` — `score_target(my_planet, candidate, fleets, comet_ids, config) → float` with components below.
- `src/orbit_wars/heuristic/sizing.py` — `ships_needed(my_planet, target, transit_turns, config) → int`.
- `src/orbit_wars/heuristic/threats.py` — `incoming_threats_for(my_planet, fleets) → list[Threat]`; `defense_priority(my_planets, threats, config) → list[(my_planet_id, ships)]`.
- `src/orbit_wars/heuristic/comets.py` — `comet_capture_priority(my_planets, comets, comet_ids, config) → list[(my_planet_id, comet_id, ships)]`.
- `src/orbit_wars/heuristic/pathing.py` — `safe_angle(from_xy, to_xy, sun_center, sun_radius) → float` that deflects around the sun if the straight line intersects.
- Remaining CLI: implement the `play`, `ladder`, `replay`, `pack` commands. `pack` is the submission packager (see §6).
- Tests: `tests/test_strategy_smoke.py` (full self-play episode completes without exception), `tests/test_pack.py` (tarball has `main.py` at root, imports cleanly, `agent()` is callable).

**Orchestrator deliverables (Tier 3):**
- Code review pass (`pensive:code-reviewer` + `parseltongue:python-linter`).
- Integration into `master` (worktree merge).
- Submission gate run (G4).
- Iteration roadmap as a tracked plan.

## 4. Phase gates

- **G1 (Phase 1 → Phase 2):** all 9 E-reports written and pass schema check (every section present, "Fetch method" set, "Goal" non-empty).
- **G2 (Phase 2 → Phase 3):** synthesis brief written to `docs/internal/findings/00-orbit-wars-synthesis.md`. **User reviews and approves before coders start.**
- **G3 (Phase 3 internal — Tier 1 → Tier 2):** C1 tests pass (`uv run pytest tests/test_geometry.py tests/test_rotation.py tests/test_sim_parity.py -q`); C3-part-1 toolchain works (`uv sync` succeeds, CUDA check completes, `uv run orbit-play --help` prints).
- **G4 (Submission gate):** `uv run orbit-play pack` produces `submission.tar.gz`; smoke test extracts it into a tempdir and runs a full `kaggle_environments` self-play episode without crash or timeout. **No submission instructions issued without G4 passing.**

## 5. v1 codebase architecture

```
src/
  main.py                          ← thin shim: `from orbit_wars.heuristic.strategy import agent`
  orbit_wars/
    __init__.py
    state.py                  (C1) typed Planet/Fleet/Comet, ObservationView
    geometry.py               (C1) distance, atan2, sun_segment_intersect, intercept_solver
    rotation.py               (C1) predict_planet_position(initial, angular_velocity, steps_ahead)
    sim.py                    (C1) fast Python sim mirroring kaggle_environments
    heuristic/                (C3) v1 SHIPS this
      __init__.py
      config.py               ← HeuristicConfig dataclass (tunable weights/thresholds)
      strategy.py             ← top-level agent(obs); main.py imports from here
      targeting.py
      sizing.py
      threats.py
      comets.py
      pathing.py
    rl/                       (C2) built in v1, NOT shipped in v1
      __init__.py
      policy.py
      env.py
      train.py
      eval.py
      remote.py               ← Modal abstraction, no-op in default `local` mode
  tools/
    __init__.py
    cli.py                    (C3) Typer app: play, ladder, replay, pack, train, eval
    pack.py                   (C3) builds submission.tar.gz with main.py at root
tests/
  test_geometry.py            (C1)
  test_rotation.py            (C1)
  test_sim_parity.py          (C1) sim matches kaggle_environments on N seeded episodes
  test_strategy_smoke.py      (C3) self-play episode completes
  test_pack.py                (C3) tarball has main.py at root, imports cleanly, agent() callable
pyproject.toml                (C3) adds kaggle-environments, gymnasium, ruff, pytest, mypy/ty,
                                   typer[all], rich, hypothesis; modal as optional [remote] extra
docs/
  internal/findings/          (Phase 1–2 outputs; user already created docs/internal/)
  superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md  (this file)
```

## 6. Submission packaging

C3's `pack` command. Default invocation (`uv run orbit-play pack`) packages a v1 (heuristic-only) submission. Add `--include-rl <checkpoint_path>` to package an RL submission.

1. Build a temp directory.
2. Copy `src/main.py` → `<tmp>/main.py`.
3. Copy `src/orbit_wars/` recursively to `<tmp>/orbit_wars/`, **excluding `src/orbit_wars/rl/`** (RL is not shipped by default).
4. If `--include-rl <checkpoint_path>` was passed:
   - Also copy `src/orbit_wars/rl/` recursively to `<tmp>/orbit_wars/rl/` (excluding any local training artifacts under `rl/checkpoints/`, `rl/runs/`, etc.).
   - Copy the named checkpoint file to `<tmp>/orbit_wars/rl/checkpoints/best.pt`.
   - The shipping `main.py` (or a separate `main_rl.py` selected via flag) loads `orbit_wars/rl/checkpoints/best.pt` at import time.
5. **Do not** copy `src/tools/` (CLI is for local development; not part of the submission).
6. `tar -czf submission.tar.gz -C <tmp> .` — `main.py` ends up at archive root.
7. Run a smoke test: extract into another tempdir, run `python -c "import sys; sys.path.insert(0, tmpdir); import main; main.agent({...minimal obs...})"`. Smoke test must pass with no exceptions.
8. Print the output path and SHA-256.

Submission command (issued by the user after G4 passes):

```bash
kaggle competitions submit orbit-wars -f submission.tar.gz -m "<version + change-summary>"
```

## 7. v1 heuristic agent design (what ships)

### 7.1 Quality bar

- Beats `random` baseline 100% of the time.
- Beats nearest-planet sniper (current `src/main.py`) ≥80% of the time over 50 self-play episodes.
- Never sends a fleet through the sun.
- Never crashes / never times out / never returns malformed actions.
- Reaches mid-leaderboard within 24–48 hours of submission (rating estimate above starting μ₀=600 with σ shrinking).

### 7.2 Components (C3 builds)

All weights and thresholds below are gathered into a single `HeuristicConfig` dataclass at `src/orbit_wars/heuristic/config.py`. Tentative initial values are listed; the week-2 self-play sweep tunes them.

1. **Target scoring** — for each `(my_planet, candidate_target)`:
    - `distance_score = 1 / (1 + distance / D_REF)` — `D_REF = 30.0` (≈ board diagonal / 4)
    - `production_score = candidate.production / 5.0`
    - `cost_score = 1 / max(1, ships_needed)`
    - `roi_score = candidate.production / max(1, ships_needed)` — primary signal
    - `sun_path_penalty = SUN_PENALTY if sun_segment_intersect((mp.x, mp.y), (c.x, c.y), CENTER, SUN_RADIUS) else 0.0` — `SUN_PENALTY = 1.0` (effectively excludes; we re-route via pathing below)
    - `comet_bonus = COMET_BONUS * (lifetime_remaining / COMET_LIFETIME_REF) if c.id in comet_ids else 0.0` — `COMET_BONUS = 0.5`, `COMET_LIFETIME_REF = 100`
    - `total = w_roi * roi_score + w_dist * distance_score + w_prod * production_score - sun_path_penalty + comet_bonus`
    - Tentative weights: `w_roi = 1.0`, `w_dist = 0.5`, `w_prod = 0.3`. Tuned in week 2.

2. **Fleet sizing** — `ships_needed = target.ships + ceil(target.production * estimated_transit_turns) + SAFETY_MARGIN`, capped at `my_planet.ships - HOME_RESERVE`. Tentative: `SAFETY_MARGIN = 2`, `HOME_RESERVE = 5` (drops to `0` if `my_planet` is not under threat in §7.2.4 and has no neighbors that need reinforcing). `MIN_LAUNCH = 3` (don't launch fleets smaller than this — too slow per the speed curve).

3. **Sun-aware pathing** — straight line from `(mp.x, mp.y)` to `(target.x, target.y)`. If `sun_segment_intersect`, pick the smaller deflection angle (clockwise vs counter-clockwise) that misses the sun by `SUN_RADIUS + 0.5`. Recompute distance for the deflected path so transit-time estimates remain honest.

4. **Threat detection** — for each enemy fleet inbound on `my_planet`:
    - Project arrival turn from `(fleet.x, fleet.y)` along `fleet.angle` at `fleet_speed(fleet.ships)` until distance to planet < planet.radius.
    - Estimated garrison at arrival: `current + my_planet.production * arrival_turn`.
    - If garrison_at_arrival < incoming.ships, mark planet as under-threat with `deficit = incoming.ships - garrison_at_arrival`.

5. **Defense reinforcement** — for each under-threat planet, find the nearest owned planet that can ship `deficit + DEFENSE_BUFFER` ships and arrive before the incoming fleet, accounting for fleet-speed scaling. Issue reinforcement before issuing offensive moves. Tentative: `DEFENSE_BUFFER = 2`.

6. **Comet priority** — when a comet is in capture range and ROI > `COMET_ROI_THRESHOLD`, preempt other targets for the launching planet (one-comet-priority-per-planet to avoid overcommit). Tentative: `COMET_ROI_THRESHOLD = 0.05` (i.e., ≥ 0.05 production per ship invested). Comets are worth biasing toward because they vanish on board exit.

7. **Fleet-size discipline** — at most 2 launches per `my_planet` per turn (preserves fleet-speed scaling — splitting into N tiny fleets cripples speed).

8. **Order of operations per turn**:
    1. Compute threats and reinforcements.
    2. Compute comet priorities.
    3. For each remaining `my_planet` with ships > MIN_LAUNCH, score all targets and launch the top-1 if affordable.
    4. Return moves list.

### 7.3 Determinism & seedability

- All tie-breaking deterministic (lex order on planet IDs).
- No `random.random()` calls in v1 strategy. (RL action sampling is its own concern in v2+.)

## 8. C2's RL scaffold (built in v1, used in v2+)

### 8.1 Environment

`gymnasium.Env` wrapping C1's `sim.py` (NOT `kaggle_environments` — too slow for hundreds of parallel rollouts). Parity gate: `tests/test_sim_parity.py` runs the same seeded episode through both engines and checks final state hashes match within tolerance.

### 8.2 Observation encoding

Variable-length planets (≤40) and fleets (~100) → padded tensor, with mask. Encoder is a small set transformer (handles permutation invariance over planets). Per-planet feature vector: `[owner_one_hot(5), x, y, radius, ships_normalized, production_normalized, is_comet, is_orbiting, predicted_x_t+10, predicted_y_t+10]`. Per-fleet feature vector: `[owner_one_hot(5), x, y, dx, dy, ships_normalized, eta_to_nearest_my_planet, eta_to_nearest_enemy_planet]`.

### 8.3 Action space

Per-planet head emitting `(angle_bucket, ship_fraction_bucket)`:
- `angle_bucket ∈ {0..31}` → angle in radians = `bucket * 2π / 32`.
- `ship_fraction_bucket ∈ {0, 1/8, 1/4, 1/2, 3/4, all}` — bucket `0` means "no launch".
- Mask: only own planets get non-zero action probabilities.

### 8.4 Algorithm

PPO with self-play league. Opponent pool stores TrueSkill ratings; each rollout samples opponent from top-k by rating. Avoids the rock-paper-scissors trap of naive self-play.

Key hyperparams (defaults; tuned later):
- `lr = 3e-4`, `gamma = 0.997` (long-horizon: 500 turns), `gae_lambda = 0.95`
- `clip_range = 0.2`, `entropy_coef = 0.01`, `value_coef = 0.5`
- `n_envs = 32`, `n_steps = 1024`, `batch_size = 4096`, `n_epochs = 6`
- Total budget for first run: 10M env-steps (~1–2.5 days on 2080 Ti). Time range widened from the more aggressive `n_epochs=4` baseline to reflect the extra optimizer passes per rollout batch; rollouts (CPU-bound Python sim) still dominate, so wall-clock impact is modest. C2 monitors per-iteration timings and revises if optimizer time exceeds 40% of iteration time.

### 8.5 Reward

- **Default:** terminal score difference, sparse. `reward = (my_total_ships - max(opponent_total_ships)) / 100.0` at episode end.
- **Optional shaped:** `--shaped-reward` adds small intermediate rewards (planets captured, ships preserved, fleets that survived). Off by default; enable only if PPO doesn't show progress in 10M steps.

### 8.6 Compute & Modal abstraction

- Default mode: local 2080 Ti, multiprocess rollouts via `gymnasium.vector.AsyncVectorEnv`.
- `--remote modal` mode: rollouts farmed to Modal workers via `remote.py` adapter. The orchestrator decides whether to flip at week-3 review based on local throughput and training progress.
- Modal cost estimate: $0.50–2/hour for mid-tier GPUs, ~100–500 training hours possible → $50–1000 range. Not committed unless the orchestrator and user agree it's needed.

### 8.7 Eval gate (for promoting RL → submission)

An RL checkpoint replaces the heuristic in submission only when:
- ≥60% win rate vs. heuristic over 100 episodes (mixed seeds, both 2-player and 4-player).
- Smoke test passes (no crashes, no timeouts).
- 10-episode sanity check on `kaggle_environments` directly (not just `sim.py`).

## 9. Iteration roadmap

| Wall-clock | Phase | Deliverable | Decision points |
|------------|-------|-------------|-----------------|
| Now → ~1 day | This session: Phases 1–3 | **v1 (heuristic) submitted** | First leaderboard placement observed |
| Week 2 (2026-05-08) | Heuristic tuning + RL data collection | Heuristic weight sweep via self-play; first RL training run | Did weight tuning move the needle? Is RL training stable? |
| Weeks 3–4 (2026-05-15) | RL stabilizes | First RL model that beats heuristic in eval | If yes → v2 submitted. If no → diagnose (reward shaping? larger model? Modal compute?) |
| Weeks 5–6 (2026-05-29) | League refinement | v3 — population-based or league-trained policy | Plateau? Try AlphaZero-style tree search at inference if 1s budget allows. |
| Weeks 7–8 (2026-06-12) | Endgame specialization | v4 — final submissions | We get 2 final-submission slots — submit best two |
| 2026-06-23 | **Final submission deadline** | — | — |
| 2026-06-23 → ~2026-07-08 | Continuous evaluation | — | Monitor leaderboard, no further submissions allowed |

## 10. Risks & mitigations

| # | Risk | Likelihood | Mitigation |
|---|------|-----------|------------|
| 1 | Top-10 not achieved | Medium-high | Codebase still compounds for next year's competition; v1+v2 alone likely yields a non-trivial finish |
| 2 | 2080 Ti + cu130 wheel incompatibility (Turing dropped) | Low-medium | C3-part-1 sanity check; fallback to cu128 wheels |
| 3 | `kaggle_environments` PyPI version diverges from Kaggle runtime | Medium | C1's `test_sim_parity.py` catches behavioral divergences early |
| 4 | Naive PPO self-play converges to RPS loops | High (without league) | League with TrueSkill matchmaking is mandatory in C2 |
| 5 | 1s/turn CPU inference too slow for chosen network size | Medium | Param budget cap: ≤1M; benchmark once and cap accordingly |
| 6 | Modal cost runs away | Low (we control flag) | Only flip with explicit user approval; budget cap per run |
| 7 | Synthesis brief drops a key finding | Medium | Each E-report committed separately; user spot-checks at G2 |
| 8 | RL training takes longer than 8 weeks | Medium | v1 (heuristic) is the safety net; we never lack a submission |
| 9 | 4-player FFA dynamics not handled in v1 heuristic | High | Acceptable — the heuristic plays a "solid 1v1" pattern even in 4P; v3/v4 adds FFA-aware logic |
| 10 | Comet expiration race conditions (comets removed before launches) | Medium | C1 tests this explicitly against `kaggle_environments` |

## 11. Open questions / decisions deferred

- **Action representation in RL.** Per-planet head vs. autoregressive decoder. C2 picks at design time; reviewable.
- **Heuristic weight values.** Set tentatively, tuned via self-play sweep in week 2.
- **Whether to use `ty` or `mypy`.** C3 picks; both are fine.
- **Whether to run worktree-isolated coders or shared-tree coders.** Approved: worktrees. Orchestrator merges.
- **License / data-usage.** Competition is Apache 2.0 / CC-BY 4.0 (per E2's eventual report). Our code is the user's own; no licensing decisions block this design.

## 12. Git / commit policy

The orchestrator does **not** run `git add`, `git commit`, or `git push` unless the user explicitly requests it. Files are written; the user commits. The orchestrator may surface "this is a natural commit boundary" suggestions at each phase gate.

## 13. Approval

- 2026-04-30 — User approved this plan ("approved").
- Next step: orchestrator invokes `superpowers:writing-plans` to translate this design into an executable implementation plan.

## Appendix A — Per-agent prompt templates (for the implementation plan)

These are templates the implementation plan will instantiate. Each prompt is self-contained because sub-agents start with no shared context.

### A.1 Explorer prompt template (E1–E4, file-section explorers)

```
You are a documentation analyst. Your task: read <FILE_PATH>, focus on the section
"<SECTION_HEADING>" (text between this heading and the next sibling-level heading or
section separator), and produce a structured Markdown report at <OUTPUT_PATH>.

Background: this is part of bootstrapping a Kaggle competition entry for "Orbit Wars,"
a real-time-strategy bot competition. Your report will feed downstream synthesis and
implementation agents who will not have access to the original source — your report
is their source of truth for this section.

Use the sequential-thinking MCP tool (mcp__sequential-thinking__sequentialthinking)
to reason through the section before writing. Think deeply.

Output schema (mandatory — every section heading must be present, even if "n/a"):

# E<N>: <slug>

## Source
<file path:section heading>

## Fetch method
Read

## Goal
<one paragraph: what is this section telling the reader?>

## Methods
<algorithms / rules / mechanics described in the section>

## Numerical params / hyperparams
<every constant: episodeSteps=500, sunRadius=10.0, etc. Be exhaustive.>

## Reusable code patterns
<code snippets shown in the section, transcribed verbatim with file:line citation>

## Reported leaderboard score
n/a (this is documentation, not a notebook)

## Anything novel worth replicating
<bullet list>

## Direct quotes / code snippets to preserve
<verbatim excerpts of any text that future agents need exactly>

## Open questions / things I couldn't determine
<bullet list of ambiguities or under-specified areas>

Constraints:
- Read the file with the Read tool.
- Do not infer beyond what's in the section. If something isn't there, list it under "Open questions."
- Cite file paths and line numbers for every claim.
- Write the report with the Write tool to the specified output path.
```

### A.2 Notebook explorer prompt template (E5–E9)

```
You are a code analyst. Your task: explore the Kaggle notebook at <NOTEBOOK_URL> and
produce a structured Markdown report at <OUTPUT_PATH>.

Background: this is part of bootstrapping a Kaggle competition entry for "Orbit Wars."
We're studying public reference notebooks to identify patterns we should adopt in our
own agent. Your report feeds downstream synthesis and implementation agents.

Fetch protocol (try in order):
1. `kaggle kernels pull <user>/<slug> --metadata -p /tmp/<slug>` then read the .ipynb.
   The slug is everything after `kaggle.com/code/<user>/`.
2. If `kaggle kernels pull` fails (auth, 404, etc.), use WebFetch on the URL.
3. Document which method worked.

Use the sequential-thinking MCP tool (mcp__sequential-thinking__sequentialthinking)
to reason through the notebook's strategy before writing. Think deeply.

Output schema (mandatory):

# E<N>: <slug>

## Source
<URL>

## Fetch method
<kaggle kernels pull | WebFetch>

## Goal
<one paragraph: what is the notebook author trying to accomplish?>

## Methods
<algorithms, data structures, network architecture if applicable>

## Numerical params / hyperparams
<every constant worth knowing>

## Reusable code patterns
<patterns, idioms, utilities we should adopt — with verbatim snippets>

## Reported leaderboard score
<if mentioned in the notebook or its title; "n/a" otherwise>

## Anything novel worth replicating
<bullet list, sorted by perceived value>

## Direct quotes / code snippets to preserve
<verbatim excerpts>

## Open questions / things I couldn't determine
<bullet list>

Constraints:
- Public Kaggle notebooks may require an authenticated kaggle CLI. The user has
  configured kaggle credentials at ~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY env.
- If both fetch methods fail, write the partial report with "Fetch method: failed"
  and document what blocked you.
- Cite cell numbers where you found code.
- Write the report with the Write tool.
```

### A.3 Coder prompt skeleton (C1, C2, C3)

```
You are <ROLE> for the Orbit Wars Kaggle competition codebase.

Read first (in order):
1. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/CLAUDE.md
2. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md
3. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/00-orbit-wars-synthesis.md

Your scope (do NOT exceed):
<scope from §3.3>

Your deliverables:
<deliverables from §3.3>

Working directory: <WORKTREE_PATH>

Discipline:
- Test-first for any non-trivial logic (use pytest).
- Use sequential-thinking MCP for non-trivial reasoning.
- Do not run `git commit` or `git push`. The user handles git.
- Stay within scope; if you discover a need that's out of scope, write it to
  <WORKTREE_PATH>/.notes/out-of-scope.md and continue.
- All Python: ruff-clean, type-annotated, Python 3.13 idioms.

Stop when: <stop condition>.
```

## Appendix B — Definitions

- **Orchestrator**: this Claude Code session. The 13th agent. Team Lead.
- **Sub-agent**: an Agent-tool invocation with a `subagent_type`. Stateless across invocations.
- **Worktree**: a separate working tree of the same git repo at `.worktrees/<name>/`, used to isolate parallel coder work.
- **G<N>**: phase gate — a hard checkpoint that blocks progression until criteria are met.
- **v1 / v2 / v3 / v4**: successive submitted-agent versions. v1 = heuristic. v2+ = RL-augmented.
