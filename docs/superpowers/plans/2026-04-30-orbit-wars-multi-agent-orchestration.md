# Orbit Wars Multi-Agent Orchestration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a 13-agent orchestration (12 sub-agents + this orchestrator) that produces a competitive v1 Orbit Wars heuristic agent and the iteration substrate (typed game model, fast Python simulator, RL training scaffold, self-play CLI, tests, packager) for v2+.

**Architecture:** Three sequential phases with hard gates. Phase 1 fans 9 explorer sub-agents in parallel (4 markdown sections + 5 Kaggle notebooks). Phase 2 is orchestrator-only synthesis. Phase 3 dispatches 3 coder sub-agents across two parallel tiers, then integrates. Each tier dispatch sends a single message containing all parallel `Agent` tool calls. Sub-agents work in isolated git worktrees; the orchestrator integrates back to `master`.

**Tech Stack:** Python 3.13, `uv`, `kaggle-environments`, PyTorch (cu130 with cu128 fallback), `gymnasium`, `typer`, `rich`, `pytest`, `hypothesis`, `ruff`, `mypy`/`ty`. Optional `modal` for remote training. Authoritative source: `docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md`.

---

## Operating ground rules

- **Git policy:** orchestrator does NOT run `git add`, `git commit`, or `git push` unless the user explicitly requests it. Files are written; user commits. Orchestrator surfaces "natural commit boundary" suggestions at each gate.
- **Gates are hard:** G1, G2, G3, G4 must pass before the next phase begins. If a gate fails, fix and re-verify; do not proceed.
- **Sub-agent prompts must be self-contained:** every dispatched sub-agent receives explicit references to read (CLAUDE.md, the spec, the synthesis brief) because they start with no shared context.
- **Worktree paths:** `.worktrees/c1-domain`, `.worktrees/c2-rl`, `.worktrees/c3-tooling`. Created by Task 3.1, removed by user (or Task 3.13) after integration.
- **Parallel dispatch:** when two or more `Agent` calls are independent, they MUST be sent in a single message (per `superpowers:dispatching-parallel-agents`).

## File Structure (final v1 state)

| Path | Created by | Responsibility |
|------|-----------|----------------|
| `pyproject.toml` (modified) | C3 part-1 | Adds `kaggle-environments`, `gymnasium`, `pytest`, `pytest-cov`, `ruff`, `mypy`/`ty`, `typer[all]`, `rich`, `hypothesis`; `modal` as `[remote]` extra |
| `src/main.py` (modified) | C3 part-2 | Thin shim: `from orbit_wars.heuristic.strategy import agent` |
| `src/orbit_wars/__init__.py` | C1 | Package marker |
| `src/orbit_wars/state.py` | C1 | Typed `Planet/Fleet/Comet`, `ObservationView` (handles dict-or-namespace obs) |
| `src/orbit_wars/geometry.py` | C1 | `dist`, `angle_between`, `sun_segment_intersect`, `intercept_solver` |
| `src/orbit_wars/rotation.py` | C1 | `predict_planet_position(initial, angular_velocity, steps_ahead)` |
| `src/orbit_wars/sim.py` | C1 | Fast Python simulator mirroring `kaggle_environments` |
| `src/orbit_wars/heuristic/__init__.py` | C3 part-2 | Package marker |
| `src/orbit_wars/heuristic/config.py` | C3 part-2 | `HeuristicConfig` dataclass (all tunable weights/thresholds) |
| `src/orbit_wars/heuristic/strategy.py` | C3 part-2 | Top-level `agent(obs)` |
| `src/orbit_wars/heuristic/targeting.py` | C3 part-2 | `score_target(...)` |
| `src/orbit_wars/heuristic/sizing.py` | C3 part-2 | `ships_needed(...)` |
| `src/orbit_wars/heuristic/threats.py` | C3 part-2 | `incoming_threats_for`, `defense_priority` |
| `src/orbit_wars/heuristic/comets.py` | C3 part-2 | `comet_capture_priority` |
| `src/orbit_wars/heuristic/pathing.py` | C3 part-2 | `safe_angle` |
| `src/orbit_wars/rl/__init__.py` | C2 | Package marker |
| `src/orbit_wars/rl/policy.py` | C2 | Actor-critic network (set/graph encoder, ≤1M params) |
| `src/orbit_wars/rl/env.py` | C2 | `gymnasium.Env` wrapping `sim.py` |
| `src/orbit_wars/rl/train.py` | C2 | PPO + self-play league + checkpointing |
| `src/orbit_wars/rl/eval.py` | C2 | Head-to-head harness (RL vs heuristic, vs random, vs older RL) |
| `src/orbit_wars/rl/remote.py` | C2 | Modal abstraction (`local` default, `--remote modal` for cloud rollouts) |
| `src/tools/__init__.py` | C3 part-1 | Package marker |
| `src/tools/cli.py` | C3 part-1 + part-2 | Typer app: `play`, `ladder`, `replay`, `pack`, `train`, `eval` |
| `src/tools/pack.py` | C3 part-2 | Builds `submission.tar.gz` with `main.py` at root; supports `--include-rl` |
| `tests/test_geometry.py` | C1 | Property tests via `hypothesis` |
| `tests/test_rotation.py` | C1 | Determinism + alignment with `kaggle_environments` |
| `tests/test_sim_parity.py` | C1 + C3 part-2 | Sim matches `kaggle_environments` on N=20 seeded episodes |
| `tests/test_strategy_smoke.py` | C3 part-2 | Full self-play episode completes |
| `tests/test_pack.py` | C3 part-2 | Tarball has `main.py` at root, imports cleanly, `agent()` callable |
| `docs/internal/findings/E1..E9-*.md` | Phase 1 explorers | One report per explorer |
| `docs/internal/findings/00-orbit-wars-synthesis.md` | Phase 2 (orchestrator) | Integrated brief |

---

## Phase 1: Exploration (9 explorers, parallel)

### Task 1.1: Pre-flight checks

**Files:** none modified. Pure verification.

- [ ] **Step 1: Verify findings directory exists**

Run: `ls /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings`
Expected: directory exists (empty is fine).

- [ ] **Step 2: Verify Kaggle CLI is authenticated**

Run: `kaggle competitions list -s "orbit wars" 2>&1 | head -5`
Expected: a row containing "orbit-wars" — confirms credentials work.
On failure: tell the user `kaggle.json` is missing or expired and stop. Do not proceed without auth — E5–E9 need it.

- [ ] **Step 3: Verify spec and CLAUDE.md are readable**

Run: `ls -la /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/CLAUDE.md`
Expected: both files exist and are non-empty.

### Task 1.2: Dispatch all 9 explorers in parallel

**Files:** none in this task; outputs land at the paths in §3.1 of the spec.

- [ ] **Step 1: Construct the file-section explorer prompt template (E1–E4)**

```
You are a documentation analyst for the Orbit Wars Kaggle competition.

Read this file at this exact section, then write a structured Markdown report:
- File: <FILE_PATH>
- Section: <SECTION_HEADING> (text from this heading until the next sibling-level heading or the next horizontal-rule separator).
- Output: write the report with the Write tool to <OUTPUT_PATH>.

Use the sequential-thinking MCP tool (mcp__sequential-thinking__sequentialthinking) to reason step-by-step through the section before writing. Think deeply.

Mandatory output schema (every section heading present, even if "n/a"):

# E<N>: <slug>

## Source
<FILE_PATH>:<SECTION_HEADING>

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
n/a

## Anything novel worth replicating
<bullet list>

## Direct quotes / code snippets to preserve
<verbatim excerpts of any text future agents need exactly>

## Open questions / things I couldn't determine
<bullet list>

Constraints:
- Read with the Read tool.
- Cite line numbers for every claim.
- Do not infer beyond what's in the section. Ambiguities go in "Open questions."
- Write the report with the Write tool to <OUTPUT_PATH>.
```

- [ ] **Step 2: Construct the notebook explorer prompt template (E5–E9)**

```
You are a code analyst for the Orbit Wars Kaggle competition.

Explore this Kaggle notebook and write a structured Markdown report:
- URL: <NOTEBOOK_URL>
- Slug (everything after kaggle.com/code/<user>/): <SLUG>
- Output: write the report with the Write tool to <OUTPUT_PATH>.

Fetch protocol (try in this order):
1. `kaggle kernels pull <USER>/<SLUG_TAIL> --metadata -p /tmp/<SLUG_TAIL>` (USER is the part between `code/` and the next `/`; SLUG_TAIL is after that). Then read the resulting `.ipynb` with the Read tool.
2. If `kaggle kernels pull` fails, fall back to WebFetch on the URL.
3. Document which method worked.

Use the sequential-thinking MCP tool (mcp__sequential-thinking__sequentialthinking) to reason through the notebook's strategy before writing. Think deeply.

Mandatory output schema (every section heading present, even if "n/a"):

# E<N>: <SLUG>

## Source
<NOTEBOOK_URL>

## Fetch method
<kaggle kernels pull | WebFetch | failed>

## Goal
<one paragraph: what is the notebook author trying to accomplish?>

## Methods
<algorithms, data structures, network architecture if applicable>

## Numerical params / hyperparams
<every constant worth knowing>

## Reusable code patterns
<patterns, idioms, utilities we should adopt — verbatim snippets with cell numbers>

## Reported leaderboard score
<if mentioned in title or notebook; "n/a" otherwise>

## Anything novel worth replicating
<bullet list, sorted by perceived value>

## Direct quotes / code snippets to preserve
<verbatim excerpts>

## Open questions / things I couldn't determine
<bullet list>

Constraints:
- If both fetch methods fail, set "Fetch method: failed", explain what blocked you, and submit a partial report.
- Cite cell numbers for every code claim.
- Write the report with the Write tool.
```

- [ ] **Step 3: Send a single message containing 9 `Agent` tool calls (parallel dispatch)**

Per agent, fill in the template parameters from the table below and call `Agent` with `subagent_type: "general-purpose"`, a short `description` (e.g., `"E1 explore competition overview"`), and the filled-in `prompt`.

| Agent | Template | Parameters |
|-------|----------|------------|
| E1 | file-section | FILE_PATH=`docs/competition_documentation/Orbit_Wars-competition_overview_and_rules.md`, SECTION_HEADING=`Orbit Wars: Kaggle Competition Overview`, OUTPUT_PATH=`docs/internal/findings/E1-competition-overview.md`, N=1, slug=`competition-overview` |
| E2 | file-section | FILE_PATH=same, SECTION_HEADING=`Orbit Wars: Kaggle Competition Rules`, OUTPUT_PATH=`docs/internal/findings/E2-competition-rules.md`, N=2, slug=`competition-rules` |
| E3 | file-section | FILE_PATH=`docs/competition_documentation/Orbit_Wars-game_and_agents_overviews.md`, SECTION_HEADING=`Orbit Wars: Game Overview`, OUTPUT_PATH=`docs/internal/findings/E3-game-overview.md`, N=3, slug=`game-overview` |
| E4 | file-section | FILE_PATH=same, SECTION_HEADING=`Orbit Wars: Agents Overview`, OUTPUT_PATH=`docs/internal/findings/E4-agents-overview.md`, N=4, slug=`agents-overview` |
| E5 | notebook | NOTEBOOK_URL=`https://www.kaggle.com/code/bovard/getting-started`, SLUG=`bovard-getting-started`, USER=`bovard`, SLUG_TAIL=`getting-started`, OUTPUT_PATH=`docs/internal/findings/E5-bovard-getting-started.md`, N=5 |
| E6 | notebook | URL=`https://www.kaggle.com/code/pilkwang/orbit-wars-structured-baseline`, SLUG=`pilkwang-structured-baseline`, USER=`pilkwang`, SLUG_TAIL=`orbit-wars-structured-baseline`, OUTPUT_PATH=`docs/internal/findings/E6-pilkwang-structured-baseline.md`, N=6 |
| E7 | notebook | URL=`https://www.kaggle.com/code/kashiwaba/orbit-wars-reinforcement-learning-tutorial`, SLUG=`kashiwaba-rl-tutorial`, USER=`kashiwaba`, SLUG_TAIL=`orbit-wars-reinforcement-learning-tutorial`, OUTPUT_PATH=`docs/internal/findings/E7-kashiwaba-rl-tutorial.md`, N=7 |
| E8 | notebook | URL=`https://www.kaggle.com/code/sigmaborov/lb-958-1-orbit-wars-2026-reinforce`, SLUG=`sigmaborov-lb958-reinforce`, USER=`sigmaborov`, SLUG_TAIL=`lb-958-1-orbit-wars-2026-reinforce`, OUTPUT_PATH=`docs/internal/findings/E8-sigmaborov-lb958-reinforce.md`, N=8 |
| E9 | notebook | URL=`https://www.kaggle.com/code/romantamrazov/orbit-star-wars-lb-max-1224`, SLUG=`romantamrazov-lb1224`, USER=`romantamrazov`, SLUG_TAIL=`orbit-star-wars-lb-max-1224`, OUTPUT_PATH=`docs/internal/findings/E9-romantamrazov-lb1224.md`, N=9 |

- [ ] **Step 4: Await all 9 completion notifications**

Each `Agent` call returns a notification when the sub-agent finishes. Do not poll; the runtime delivers notifications as user-role messages.

### Task 1.3: G1 — verify outputs

**Files:** read-only verification of `docs/internal/findings/E*.md`.

- [ ] **Step 1: Confirm all 9 files exist**

Run: `ls -la /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/`
Expected: `E1-…md` through `E9-…md` all present, all non-zero size.

- [ ] **Step 2: Verify mandatory schema in each file**

Run: `for f in /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/E*.md; do echo "== $f =="; for h in "## Source" "## Fetch method" "## Goal" "## Methods" "## Numerical params" "## Reusable code patterns" "## Reported leaderboard score" "## Anything novel worth replicating" "## Direct quotes" "## Open questions"; do grep -q "$h" "$f" && echo "  OK: $h" || echo "  MISSING: $h"; done; done`
Expected: every file shows OK for every heading. Any MISSING → re-dispatch that explorer with a correction note.

- [ ] **Step 3: Spot-check fetch method on notebook explorers**

Run: `grep -A1 "## Fetch method" /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/E[5-9]*.md`
Expected: `kaggle kernels pull` (preferred) or `WebFetch`. If any show `failed`, surface to user before proceeding — synthesis quality drops without that source.

- [ ] **Step 4: Surface G1 status to user**

Tell the user: "G1 passed — 9 explorer reports written and schema-clean. Ready for synthesis. Natural commit boundary: `git add docs/internal/findings/E*.md` if you want to checkpoint." Wait for user acknowledgment.

---

## Phase 2: Synthesis (orchestrator only)

### Task 2.1: Read all 9 reports and reason through synthesis

**Files:** read-only.

- [ ] **Step 1: Read all 9 reports in parallel**

Send a single message with 9 `Read` tool calls — one per `docs/internal/findings/E<N>-*.md`.

- [ ] **Step 2: Use sequential-thinking to structure the synthesis**

Use `mcp__sequential-thinking__sequentialthinking` to plan the integrated brief: identify cross-notebook patterns, conflicts, and adoption decisions. Think deeply.

### Task 2.2: Write the synthesis brief

**Files:** Create `docs/internal/findings/00-orbit-wars-synthesis.md`.

- [ ] **Step 1: Draft the brief with the 5 mandatory sections**

Write to `docs/internal/findings/00-orbit-wars-synthesis.md`. Required sections:

```markdown
# Orbit Wars — Integrated Findings & Adoption Plan

## 1. Rules & Constraints Codex
[from E1+E2: every numeric parameter, every game rule, every submission constraint, every legal restriction. Cross-reference to source.]

## 2. Game Mechanics & Agent Contract Codex
[from E3+E4: formal state space, action space, dynamics, scoring, agent function signature, observation field reference, named-tuple imports.]

## 3. Cross-Notebook Pattern Table
[rows = patterns/techniques, columns = (bovard, pilkwang, kashiwaba, sigmaborov, romantamrazov); cells = "yes/no/variant" with brief notes. Highlight scores.]

## 4. Adoption Decisions
[for each pattern: "adopt in v1 / consider for v2 / skip" + reasoning.]

## 5. Actionable Recommendations (3–9 items, prioritized, mapped to C1/C2/C3)
[concrete, prioritized, with the responsible coder annotated.]
```

- [ ] **Step 2: Self-review the brief**

Verify: every E-report contributed at least one row to §3; every recommendation in §5 is mapped to C1, C2, or C3; no "TBD" or "TODO"; consistent terminology with the spec.

### Task 2.3: G2 — user review

**Files:** none.

- [ ] **Step 1: Surface G2 to user**

Tell the user: "Synthesis brief written to `docs/internal/findings/00-orbit-wars-synthesis.md`. Please review §3 (cross-notebook patterns) and §5 (recommendations) — those drive coder priorities. Reply 'approved' to proceed to Phase 3, or tell me what to revise. Natural commit boundary: `git add docs/internal/findings/00-orbit-wars-synthesis.md`." Wait for approval.

---

## Phase 3 — Tier 1: Foundation (parallel: C1 + C3 part-1)

### Task 3.1: Create coder worktrees

**Files:** new `.worktrees/c1-domain`, `.worktrees/c3-tooling`, `.worktrees/c2-rl` directories (each is a separate working tree of `master`).

- [ ] **Step 1: Verify the working tree is clean enough to branch from**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && git status --short`
Expected: any output is fine; we won't branch *from* uncommitted state, but worktrees branch from `HEAD`. If `HEAD` doesn't exist (no commits), tell the user to make an initial commit first and stop.

- [ ] **Step 2: Create C1 worktree**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && git worktree add .worktrees/c1-domain -b orchestration/c1-domain`
Expected: `Preparing worktree (new branch 'orchestration/c1-domain')`.

- [ ] **Step 3: Create C3 tooling worktree**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && git worktree add .worktrees/c3-tooling -b orchestration/c3-tooling`
Expected: same shape.

- [ ] **Step 4: Create C2 RL worktree (used in Tier 2; create now to keep setup atomic)**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && git worktree add .worktrees/c2-rl -b orchestration/c2-rl`
Expected: same shape.

- [ ] **Step 5: Verify worktree list**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && git worktree list`
Expected: 4 entries (master + 3 worktrees).

### Task 3.2: Dispatch C1 (domain + simulator) — parallel with 3.3

**Files:** sub-agent will create files inside `.worktrees/c1-domain/`. Specifically: `src/orbit_wars/__init__.py`, `state.py`, `geometry.py`, `rotation.py`, `sim.py`, plus tests.

- [ ] **Step 1: Compose the C1 prompt**

```
You are C1 — Domain Model & Simulator for the Orbit Wars Kaggle competition codebase.

READ FIRST (in order):
1. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/CLAUDE.md
2. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md (focus on §3.3 C1 deliverables, §5 file tree, §7 heuristic dependencies on geometry/rotation, §8.1 sim parity requirements)
3. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/00-orbit-wars-synthesis.md (notebook patterns relevant to game model)
4. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/competition_documentation/Orbit_Wars-game_and_agents_overviews.md (canonical game rules)

WORKING DIRECTORY: /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c1-domain

YOUR SCOPE — do NOT exceed:
Build the domain model, geometry primitives, rotation predictor, and a fast Python simulator that mirrors `kaggle_environments.envs.orbit_wars` semantics for RL rollouts.

DELIVERABLES (exact files):
- src/orbit_wars/__init__.py — package marker, version string.
- src/orbit_wars/state.py — typed Planet, Fleet, Comet (frozen dataclasses); ObservationView that handles both dict and namespace observations uniformly. Re-export the named tuples from `kaggle_environments.envs.orbit_wars.orbit_wars` (Planet, Fleet, CENTER, ROTATION_RADIUS_LIMIT) where useful.
- src/orbit_wars/geometry.py — `dist(p1, p2) -> float`, `angle_between(from_xy, to_xy) -> float`, `sun_segment_intersect(p1, p2, sun_center=(50,50), sun_radius=10.0) -> bool`, `intercept_solver(launcher_xy, target_initial_xy, target_velocity_xy_per_turn, fleet_speed) -> (angle, eta) | None`.
- src/orbit_wars/rotation.py — `predict_planet_position(initial_planet, angular_velocity, steps_ahead, center=(50,50)) -> (x, y)`. Use ROTATION_RADIUS_LIMIT for the "is this planet orbiting?" check.
- src/orbit_wars/sim.py — fast Python simulator class `OrbitWarsSim` mirroring `kaggle_environments` orbit_wars semantics: turn order (comet expiration → comet spawn → fleet launch → production → fleet movement → planet rotation/comet movement → combat resolution), state-hash function for parity testing, episode reset with seed.
- tests/test_geometry.py — exercise distance, angle, sun-segment-intersect (corners, tangent, through-sun cases). Use `hypothesis` for property tests where applicable (distance is symmetric; angle in [-π, π]; etc.).
- tests/test_rotation.py — verify `predict_planet_position(p, av, 0)` returns initial position; verify rotation direction; verify static-planet predictions are constant.
- tests/test_sim_parity.py — N=20 seeded episodes through both `OrbitWarsSim` and `kaggle_environments.make("orbit_wars")` with the same agent (use a deterministic stub that returns `[]`); compare per-step state hashes; allow small float tolerance. Mark slow with `@pytest.mark.slow`.

DISCIPLINE:
- Test-first: write each test before its implementation.
- All Python: ruff-clean, type-annotated, Python 3.13 idioms, frozen dataclasses where appropriate.
- Use sequential-thinking MCP for non-trivial reasoning (intercept solver, sim turn order).
- Do NOT run `git add`, `git commit`, or `git push`. The user handles git.
- Do NOT install/sync deps — C3 part-1 owns pyproject.toml. Use `python -m pytest` if needed; assume `kaggle-environments`, `pytest`, `hypothesis` are available (orchestrator pre-installs if missing — see verification step).
- If you discover a need outside scope, write it to .worktrees/c1-domain/.notes/out-of-scope.md and continue.

STOP WHEN: all listed files exist, all tests written, and you can show that `python -m pytest tests/test_geometry.py tests/test_rotation.py -q` passes (sim parity test may be slow; mark `@pytest.mark.slow` and run only on explicit request).

Return a one-paragraph summary of what was built and any out-of-scope notes filed.
```

- [ ] **Step 2: Verify required deps for C1's tests are installed in the working venv before dispatch**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && uv run python -c "import kaggle_environments, pytest, hypothesis" 2>&1 | head -20`
If `ImportError: kaggle_environments`: run `uv add kaggle-environments hypothesis pytest` (this is C3-part-1's job formally, but C1's parity test needs it now). If still failing: skip the parity test for now and let C3-part-1 add it; C1's other tests don't need these deps.

### Task 3.3: Dispatch C3 part-1 (toolchain bootstrap) — parallel with 3.2

**Files:** sub-agent modifies `.worktrees/c3-tooling/pyproject.toml`, creates `.worktrees/c3-tooling/src/tools/__init__.py`, `cli.py` (stub).

- [ ] **Step 1: Compose the C3 part-1 prompt**

```
You are C3 part-1 — Toolchain Bootstrap for the Orbit Wars Kaggle competition codebase.

READ FIRST (in order):
1. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/CLAUDE.md
2. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md (focus on §3.3 C3 part-1 deliverables, §5 file tree, §6 packaging)

WORKING DIRECTORY: /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling

YOUR SCOPE — do NOT exceed:
Bootstrap dependencies, CUDA sanity check, Typer CLI scaffold. The CLI commands are stubbed in this part; C3 part-2 fills them in.

DELIVERABLES (exact files / changes):
- pyproject.toml: ADD dependencies (use `uv add` to update both pyproject.toml and uv.lock):
    - `kaggle-environments` (regular dep — `src/main.py` imports it)
    - `gymnasium` (regular dep — needed by C2 in Tier 2)
    - `pytest`, `pytest-cov`, `hypothesis` (dev deps — `[tool.uv] dev-dependencies`)
    - `ruff`, `mypy` (dev deps; you may use `ty` instead of mypy if you prefer — document which)
    - `typer[all]`, `rich` (regular deps — needed by the CLI)
    - `modal` as an OPTIONAL dependency: add `[project.optional-dependencies]\nremote = ["modal"]`
- pyproject.toml: ADD `[project.scripts]\norbit-play = "tools.cli:app"` so `uv run orbit-play` works.
- src/tools/__init__.py — package marker.
- src/tools/cli.py — Typer app with stub commands `play`, `ladder`, `replay`, `pack`, `train`, `eval`. Each prints "TODO: <command> — implemented in C3 part-2 / C2" and exits 0. Use Rich for any output formatting.
- A one-line CUDA sanity-check command in the README of your worktree (`.worktrees/c3-tooling/CUDA_CHECK.md`): the command, its expected output on the user's RTX 2080 Ti (cu130 should support sm_75; if not, fallback to cu128 wheels — document the fallback procedure).
- Run `uv sync` and verify `uv run orbit-play --help` prints the command list.
- Run the CUDA sanity check yourself: `uv run python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only'); t = torch.zeros(1, device='cuda' if torch.cuda.is_available() else 'cpu'); print('Tensor device:', t.device)"`. Document the actual output in CUDA_CHECK.md. If CUDA is unavailable but the user expects it: troubleshoot LD_LIBRARY_PATH (see CLAUDE.md §Toolchain) and direnv.

DISCIPLINE:
- All Python: ruff-clean, type-annotated, Python 3.13 idioms.
- Use sequential-thinking MCP if you encounter dependency-resolution conflicts (cu130 + RAPIDS 26.2 is a tight matrix).
- Do NOT run `git add`, `git commit`, or `git push`.
- If `uv add kaggle-environments` triggers a resolver conflict with cu130 RAPIDS: document the conflict in `.notes/out-of-scope.md` and propose either (a) downgrading specific RAPIDS pins, (b) splitting RAPIDS into a `[gpu]` optional group, or (c) dropping RAPIDS entirely if it's unused. Do NOT make this decision yourself — surface to orchestrator.

STOP WHEN: `uv sync` succeeds; `uv run orbit-play --help` works; CUDA_CHECK.md is written with actual measured output.

Return a one-paragraph summary of what was added and the actual CUDA-check output.
```

- [ ] **Step 2: Send a single message with both `Agent` calls (Task 3.2 + Task 3.3 in parallel)**

Compose two `Agent` tool calls in one message:
- C1: `subagent_type="parseltongue:python-pro"`, prompt from Task 3.2 Step 1.
- C3-part-1: `subagent_type="python3-development:python-cli-architect"`, prompt from Task 3.3 Step 1.

- [ ] **Step 3: Await both completion notifications**

### Task 3.4: G3 — verify Tier 1

**Files:** read-only verification.

- [ ] **Step 1: Verify C1 file tree**

Run: `find /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c1-domain/src/orbit_wars -name "*.py" | sort`
Expected: at minimum `__init__.py`, `state.py`, `geometry.py`, `rotation.py`, `sim.py`.

- [ ] **Step 2: Verify C1 tests pass**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c1-domain && uv run pytest tests/test_geometry.py tests/test_rotation.py -q`
Expected: all pass. The parity test (`test_sim_parity.py`) is `@pytest.mark.slow` — run separately: `uv run pytest tests/test_sim_parity.py -q -m slow`. If parity fails on >2/20 episodes, dispatch a follow-up to C1 with the failing seeds.

- [ ] **Step 3: Verify C3 part-1 toolchain**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling && uv sync && uv run orbit-play --help`
Expected: `--help` lists `play`, `ladder`, `replay`, `pack`, `train`, `eval`.

- [ ] **Step 4: Verify CUDA check was performed**

Run: `cat /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling/CUDA_CHECK.md`
Expected: actual measured output (`CUDA available: True`, `Device: NVIDIA GeForce RTX 2080 Ti`, etc.). If `False`: surface to user — likely `LD_LIBRARY_PATH`/direnv issue per CLAUDE.md.

- [ ] **Step 5: Surface G3 to user**

Tell user: "G3 passed — C1 (domain+sim) and C3 part-1 (toolchain) complete and tested in their worktrees. Ready for Tier 2 (C2 RL + C3 part-2 heuristic). Natural commit boundary in each worktree."

---

## Phase 3 — Tier 2: Implementation (parallel: C2 + C3 part-2)

### Task 3.5: Pre-merge C1's domain into C2 and C3 worktrees

**Files:** copy C1's `src/orbit_wars/{state,geometry,rotation,sim}.py` and `tests/test_*.py` into both `.worktrees/c2-rl/` and `.worktrees/c3-tooling/`.

C2 and C3 part-2 both consume C1's domain model. Rather than have them re-implement, copy C1's outputs into their worktrees as a starting point. (User merges everything later via Task 3.10.)

- [ ] **Step 1: Sync C1 → c2-rl**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && cp -r .worktrees/c1-domain/src/orbit_wars .worktrees/c2-rl/src/ && cp .worktrees/c1-domain/tests/test_geometry.py .worktrees/c1-domain/tests/test_rotation.py .worktrees/c1-domain/tests/test_sim_parity.py .worktrees/c2-rl/tests/`
Then run: `cd .worktrees/c2-rl && uv run pytest tests/test_geometry.py tests/test_rotation.py -q` — expect pass.

- [ ] **Step 2: Sync C1 → c3-tooling**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && cp -r .worktrees/c1-domain/src/orbit_wars .worktrees/c3-tooling/src/ && cp .worktrees/c1-domain/tests/test_geometry.py .worktrees/c1-domain/tests/test_rotation.py .worktrees/c1-domain/tests/test_sim_parity.py .worktrees/c3-tooling/tests/`
Then run: `cd .worktrees/c3-tooling && uv run pytest tests/test_geometry.py tests/test_rotation.py -q` — expect pass.

### Task 3.6: Dispatch C2 (RL scaffold) — parallel with 3.7

**Files:** sub-agent creates files inside `.worktrees/c2-rl/src/orbit_wars/rl/`.

- [ ] **Step 1: Compose the C2 prompt**

```
You are C2 — RL Training Scaffold for the Orbit Wars Kaggle competition codebase.

READ FIRST (in order):
1. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/CLAUDE.md
2. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md (focus on §3.3 C2 deliverables, §8 RL design — env, policy, action space, PPO hyperparams, eval gate)
3. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/00-orbit-wars-synthesis.md (especially patterns from kashiwaba, sigmaborov, romantamrazov — RL-leaning notebooks)
4. The original full reports for those notebooks: docs/internal/findings/E7-kashiwaba-rl-tutorial.md, E8-sigmaborov-lb958-reinforce.md, E9-romantamrazov-lb1224.md

WORKING DIRECTORY: /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c2-rl

CONSULTANT: when reviewing your network architecture or PPO implementation, dispatch a sub-agent of type `yzmir-pytorch-engineering:pytorch-code-reviewer` for a review pass before declaring done.

YOUR SCOPE — do NOT exceed:
Build the RL training scaffold (policy, env, train, eval, remote). Build it; do NOT train a model in this session — training is post-this-task work the user runs separately.

DELIVERABLES (exact files):
- src/orbit_wars/rl/__init__.py — package marker.
- src/orbit_wars/rl/policy.py — actor-critic with set/graph encoder over planets+fleets. Param budget: ≤1M total. Per spec §8.2: per-planet feature vector includes [owner_one_hot(5), x, y, radius, ships_norm, prod_norm, is_comet, is_orbiting, predicted_x_t+10, predicted_y_t+10]; per-fleet [owner_one_hot(5), x, y, dx, dy, ships_norm, eta_to_nearest_my_planet, eta_to_nearest_enemy_planet]. Output: per-planet head emitting (angle_bucket, ship_fraction_bucket). MUST export a top-level `build_policy(config: PolicyConfig | None = None) -> nn.Module` factory function (the orchestrator verifies param count via this entrypoint).
- src/orbit_wars/rl/env.py — gymnasium.Env wrapping `orbit_wars.sim.OrbitWarsSim`. Action space per spec §8.3: per-planet (angle ∈ 32 buckets, ship-fraction ∈ {0,1/8,1/4,1/2,3/4,all}; bucket 0 = no launch). Mask invalid actions (only own planets get non-zero probabilities).
- src/orbit_wars/rl/train.py — PPO with self-play league. Defaults from spec §8.4: lr=3e-4, gamma=0.997, gae_lambda=0.95, clip_range=0.2, entropy_coef=0.01, value_coef=0.5, n_envs=32, n_steps=1024, batch_size=4096, n_epochs=6. Total step budget: 10M (CLI flag). Opponent pool with TrueSkill matchmaking, top-k sampling. Checkpoint every 100k steps to `runs/<run_id>/checkpoints/`. Resume from checkpoint via `--resume`.
- src/orbit_wars/rl/eval.py — head-to-head harness. `evaluate(checkpoint, opponent="heuristic"|"random"|"path/to/other.pt", n_episodes=100) -> {win_rate, score_margin, episodes}`.
- src/orbit_wars/rl/remote.py — Modal abstraction. Default `local` mode runs everything in-process with `gymnasium.vector.AsyncVectorEnv`. `--remote modal` mode farms rollouts to Modal workers; lazy-import `modal` so it's not required for local use. Provide a clear "use the modal-serverless-gpu skill to set up your Modal account" comment in the docstring.
- tests/test_rl_policy.py — verify forward pass shape; verify param count ≤1M; verify mask zeroes-out non-own-planet actions.
- tests/test_rl_env.py — verify observation tensor shape; verify reset returns valid obs; verify step accepts all action types and returns (obs, reward, done, truncated, info).

DISCIPLINE:
- Test-first.
- All Python: ruff-clean, type-annotated, Python 3.13 idioms.
- Use sequential-thinking MCP for the policy architecture and reward shaping.
- Do NOT train models. Do NOT run >100 env-steps in any test. Tests must complete in <60s total.
- Do NOT run `git add`, `git commit`, or `git push`.
- After your initial implementation, dispatch `yzmir-pytorch-engineering:pytorch-code-reviewer` on `src/orbit_wars/rl/` for a review; apply its critical-severity feedback.

STOP WHEN: all listed files exist; `uv run pytest tests/test_rl_*.py -q` passes; pytorch-code-reviewer review applied.

Return a one-paragraph summary of architecture choices, param count, and the consultant's review verdict.
```

### Task 3.7: Dispatch C3 part-2 (heuristic + tests + packager) — parallel with 3.6

**Files:** sub-agent creates files inside `.worktrees/c3-tooling/src/orbit_wars/heuristic/` and modifies `src/main.py`, `src/tools/cli.py`, creates `src/tools/pack.py` and tests.

- [ ] **Step 1: Compose the C3 part-2 prompt**

```
You are C3 part-2 — v1 Heuristic Agent + CLI + Tests + Packager for the Orbit Wars Kaggle competition codebase.

READ FIRST (in order):
1. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/CLAUDE.md
2. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md (focus on §3.3 C3 part-2 deliverables, §5 file tree, §6 packaging, §7 v1 heuristic — every component and tentative constant value)
3. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/00-orbit-wars-synthesis.md (cross-notebook strategy patterns)
4. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/E5-bovard-getting-started.md (official starter — note any gotchas)
5. /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/internal/findings/E6-pilkwang-structured-baseline.md (heuristic patterns)
6. The current src/main.py (the placeholder nearest-planet sniper)

WORKING DIRECTORY: /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling

YOUR SCOPE — do NOT exceed:
Build the v1 heuristic agent (the actual ship), the rest of the Typer CLI, tests, and the submission packager.

DELIVERABLES (exact files):
- src/main.py — REPLACE the existing nearest-planet sniper with a thin shim:
    ```python
    """Orbit Wars submission entry point. The agent function lives in orbit_wars.heuristic.strategy."""
    from orbit_wars.heuristic.strategy import agent

    __all__ = ["agent"]
    ```
- src/orbit_wars/heuristic/__init__.py — package marker.
- src/orbit_wars/heuristic/config.py — `HeuristicConfig` dataclass collecting all tunable weights and thresholds. Use the tentative initial values from spec §7.2: D_REF=30.0, SUN_PENALTY=1.0, COMET_BONUS=0.5, COMET_LIFETIME_REF=100, w_roi=1.0, w_dist=0.5, w_prod=0.3, SAFETY_MARGIN=2, HOME_RESERVE=5, MIN_LAUNCH=3, DEFENSE_BUFFER=2, COMET_ROI_THRESHOLD=0.05.
- src/orbit_wars/heuristic/strategy.py — top-level `agent(obs)`. Order of operations per spec §7.2.8: threats/reinforcements → comet priorities → offensive launches. Return list of `[from_planet_id, angle, num_ships]`. Deterministic tie-breaking (lex on planet IDs).
- src/orbit_wars/heuristic/targeting.py — `score_target(my_planet, candidate, fleets, comet_ids, config)` per spec §7.2.1.
- src/orbit_wars/heuristic/sizing.py — `ships_needed(my_planet, target, transit_turns, config)` per spec §7.2.2 with MIN_LAUNCH lower bound.
- src/orbit_wars/heuristic/threats.py — `incoming_threats_for(my_planet, fleets) -> list[Threat]`; `defense_priority(my_planets, threats, config) -> list[(my_planet_id, target_planet_id, ships)]` per spec §7.2.4 + §7.2.5.
- src/orbit_wars/heuristic/comets.py — `comet_capture_priority(my_planets, comets, comet_ids, config) -> list[(my_planet_id, comet_id, ships)]` per spec §7.2.6.
- src/orbit_wars/heuristic/pathing.py — `safe_angle(from_xy, to_xy, sun_center=(50,50), sun_radius=10.0) -> float` per spec §7.2.3.
- src/tools/cli.py — REPLACE stubs with implementations:
    - `play --opponent random|heuristic|/path/to/agent.py --episodes N --seed S`: run N episodes via `kaggle_environments`, print scores, optionally save replay JSON.
    - `ladder --opponents heuristic,nearest_sniper,random --episodes-per-opponent N`: round-robin local ladder, print win-rate matrix using Rich.
    - `replay /path/to/episode.json`: pretty-print episode summary with Rich.
    - `pack [--include-rl /path/to/checkpoint.pt] [--out submission.tar.gz]`: build submission per spec §6.
    - `train`: forward to `orbit_wars.rl.train.main(...)` (only works after C2 lands).
    - `eval`: forward to `orbit_wars.rl.eval.evaluate(...)` (only works after C2 lands).
- src/tools/pack.py — submission packager per spec §6. Steps 1-8 in spec. Smoke test must extract tarball, import main, and call `agent(minimal_obs)` without exception. Print path + SHA-256.
- tests/test_strategy_smoke.py — `def test_full_episode_completes()`: run a full self-play episode via `kaggle_environments.make("orbit_wars")`, env.run(["src/main.py", "src/main.py"]); assert no exceptions, both rewards are finite numbers, episode completed (steps == 500 or one-player elimination).
- tests/test_pack.py — `def test_pack_v1()`: invoke `tools.pack.pack(include_rl=None, out=tmpdir/"submission.tar.gz")`; extract; verify `main.py` exists at root; `python -c "import sys; sys.path.insert(0, extracted); import main; assert callable(main.agent)"`. `def test_pack_excludes_rl_by_default()`: verify no `orbit_wars/rl/` in the tarball when `--include-rl` not set.

DISCIPLINE:
- Test-first.
- All Python: ruff-clean, type-annotated, Python 3.13 idioms, frozen dataclasses where appropriate.
- Use sequential-thinking MCP for the strategy logic (target scoring + reinforcement vs. offense ordering is non-trivial).
- Do NOT run `git add`, `git commit`, or `git push`.
- The heuristic must NEVER crash, NEVER time out (1s/turn budget), NEVER return malformed actions. Add defensive checks at the agent boundary that wrap exceptions and return [] on failure (logged via `print(... file=sys.stderr)` per spec; the Kaggle harness captures stderr).

STOP WHEN: all listed files exist; `uv run pytest -q` passes (geometry+rotation+strategy_smoke+pack); `uv run orbit-play play --opponent random --episodes 1` completes without error; `uv run orbit-play pack` produces submission.tar.gz that itself self-tests.

Return a one-paragraph summary of strategy decisions and the actual leaderboard quality bar achieved (win-rate vs nearest-planet sniper from a 50-episode local ladder).
```

- [ ] **Step 2: Send a single message with both `Agent` calls (Task 3.6 + Task 3.7 in parallel)**

Compose two `Agent` tool calls in one message:
- C2: `subagent_type="parseltongue:python-pro"`, prompt from Task 3.6 Step 1.
- C3-part-2: `subagent_type="python3-development:python-cli-architect"`, prompt from Task 3.7 Step 1.

- [ ] **Step 3: Await both completion notifications**

### Task 3.8: Verify Tier 2

**Files:** read-only verification.

- [ ] **Step 1: Verify C2 RL files exist and small tests pass**

Run: `find /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c2-rl/src/orbit_wars/rl -name "*.py" | sort && cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c2-rl && uv run pytest tests/test_rl_policy.py tests/test_rl_env.py -q`
Expected: 5 RL files (policy, env, train, eval, remote) and tests pass.

- [ ] **Step 2: Verify C2 param count cap**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c2-rl && uv run python -c "from orbit_wars.rl.policy import build_policy; p = build_policy(); n = sum(t.numel() for t in p.parameters()); print(f'params={n:_}'); assert n <= 1_000_000, n"`
Expected: prints `params=<≤1_000_000>` and exits 0.

- [ ] **Step 3: Verify C3 part-2 heuristic files**

Run: `find /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling/src/orbit_wars/heuristic -name "*.py" | sort`
Expected: `__init__.py, comets.py, config.py, pathing.py, sizing.py, strategy.py, targeting.py, threats.py`.

- [ ] **Step 4: Verify C3 part-2 tests pass**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling && uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Verify a real episode runs**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling && uv run orbit-play play --opponent random --episodes 1`
Expected: prints final scores, no exceptions, exit 0.

- [ ] **Step 6: Verify quality bar (heuristic vs nearest sniper)**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling && uv run orbit-play ladder --opponents nearest_sniper,random --episodes-per-opponent 50`
Expected: heuristic wins ≥80% vs `nearest_sniper`, 100% vs `random`. If below: dispatch a follow-up to C3 part-2 with the failing seeds and a "tune weights or fix bug" directive.

- [ ] **Step 7: Surface Tier 2 status to user**

Tell user: "Tier 2 complete — C2 RL scaffold built (param count <X>, tests pass) and C3 part-2 heuristic ships (vs nearest sniper: <Y>%, vs random: <Z>%). Ready for Tier 3 integration."

---

## Phase 3 — Tier 3: Integration & submission gate

### Task 3.9: Code review pass

**Files:** read-only on worktrees.

- [ ] **Step 1: Dispatch `pensive:code-reviewer` on C2's worktree**

Send `Agent` with `subagent_type="pensive:code-reviewer"` and prompt:

```
Review the Python code under /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c2-rl/src/orbit_wars/rl/ for: bug detection, API consistency, test coverage of the policy/env/train/eval/remote modules, and pytorch-specific anti-patterns. Output a triaged list (critical / major / minor / nit). Do not run tests; assume they pass. Reference: docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md §8.
```

- [ ] **Step 2: Dispatch `pensive:code-reviewer` on C3's worktree (parallel with Step 1)**

Send `Agent` with `subagent_type="pensive:code-reviewer"` and prompt:

```
Review the Python code under /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling/src/orbit_wars/heuristic/ AND /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c3-tooling/src/tools/ for: bug detection (especially in the strategy and pack), API consistency, test coverage. Output a triaged list (critical / major / minor / nit). Reference: docs/superpowers/specs/2026-04-30-orbit-wars-multi-agent-orchestration-design.md §6 + §7.
```

- [ ] **Step 3: Send Steps 1–2 in a single message**

- [ ] **Step 4: Triage findings**

For each `critical` or `major` finding, decide: fix now (dispatch a focused follow-up to the relevant coder) or defer to v1.1 (record in `docs/internal/findings/post-v1-followups.md`). Block submission on any unfixed `critical`.

### Task 3.10: Linter pass

**Files:** modifies code in both worktrees if linter agent applies fixes.

- [ ] **Step 1: Dispatch `parseltongue:python-linter` on c2-rl**

Send `Agent` with `subagent_type="parseltongue:python-linter"` and prompt:

```
Run `ruff check` on /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c2-rl/. Apply auto-fixes (`ruff check --fix --unsafe-fixes` only if no semantic risk; otherwise `--fix` only). Then `ruff format`. Report what was fixed and what (if anything) remains. Do NOT add per-file-ignores or noqa comments to silence warnings. Do NOT commit.
```

- [ ] **Step 2: Dispatch `parseltongue:python-linter` on c3-tooling (parallel)**

Same prompt with path swapped to `.worktrees/c3-tooling/`.

- [ ] **Step 3: Send Steps 1–2 in a single message**

- [ ] **Step 4: Re-run tests to verify lint fixes didn't break anything**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.worktrees/c2-rl && uv run pytest -q && cd ../c3-tooling && uv run pytest -q`
Expected: all pass.

### Task 3.11: Worktree integration onto `master`

**Files:** copies code from worktrees into the main working tree.

- [ ] **Step 1: Stage C1's domain into the main tree**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && mkdir -p src/orbit_wars && cp -r .worktrees/c1-domain/src/orbit_wars/* src/orbit_wars/ && cp -r .worktrees/c1-domain/tests/test_geometry.py .worktrees/c1-domain/tests/test_rotation.py .worktrees/c1-domain/tests/test_sim_parity.py tests/ 2>/dev/null || mkdir -p tests && cp .worktrees/c1-domain/tests/test_*.py tests/`
Expected: `src/orbit_wars/{state,geometry,rotation,sim}.py` and `tests/test_geometry.py`, `test_rotation.py`, `test_sim_parity.py` in the main tree.

- [ ] **Step 2: Stage C3 part-1 toolchain (pyproject.toml is the load-bearing piece)**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && cp .worktrees/c3-tooling/pyproject.toml ./pyproject.toml && cp .worktrees/c3-tooling/uv.lock ./uv.lock && mkdir -p src/tools && cp -r .worktrees/c3-tooling/src/tools/* src/tools/ && cp .worktrees/c3-tooling/CUDA_CHECK.md docs/internal/`
Expected: pyproject.toml/uv.lock updated, src/tools/ populated.

- [ ] **Step 3: Stage C3 part-2 heuristic + main shim**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && cp -r .worktrees/c3-tooling/src/orbit_wars/heuristic src/orbit_wars/ && cp .worktrees/c3-tooling/src/main.py src/main.py && cp .worktrees/c3-tooling/tests/test_strategy_smoke.py .worktrees/c3-tooling/tests/test_pack.py tests/`
Expected: heuristic package + new main.py + smoke/pack tests.

- [ ] **Step 4: Stage C2 RL scaffold**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && cp -r .worktrees/c2-rl/src/orbit_wars/rl src/orbit_wars/ && cp .worktrees/c2-rl/tests/test_rl_policy.py .worktrees/c2-rl/tests/test_rl_env.py tests/`
Expected: rl package + RL tests.

- [ ] **Step 5: Sync and run all tests on the integrated tree**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && uv sync && uv run pytest -q`
Expected: all pass except `@pytest.mark.slow` (parity test). Run parity separately: `uv run pytest tests/test_sim_parity.py -m slow -q`.

- [ ] **Step 6: Surface integration status to user**

Tell user: "Integration complete on master. All tests pass. Worktrees still exist at `.worktrees/c1-domain`, `.worktrees/c2-rl`, `.worktrees/c3-tooling`; you can `git worktree remove` them after committing the integrated tree. Natural commit boundary: this is the v1 codebase ready for the submission gate."

### Task 3.12: G4 — submission gate

**Files:** none (consumes `submission.tar.gz`).

- [ ] **Step 1: Build the submission tarball**

Run: `cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars && uv run orbit-play pack --out submission.tar.gz`
Expected: `submission.tar.gz` created; SHA-256 printed; built-in smoke test passes.

- [ ] **Step 2: Verify tarball structure**

Run: `tar -tzf /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/submission.tar.gz | sort | head -30`
Expected: `./main.py` at root; `./orbit_wars/...` package; NO `./orbit_wars/rl/`; NO `./tools/`.

- [ ] **Step 3: Independent self-play smoke test**

Run:
```bash
cd /tmp && rm -rf ow_smoke && mkdir ow_smoke && tar -xzf /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/submission.tar.gz -C ow_smoke && cd ow_smoke && /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from kaggle_environments import make
env = make('orbit_wars', debug=False)
env.run(['main.py', 'main.py'])
print('rewards:', [s.reward for s in env.steps[-1]])
print('statuses:', [s.status for s in env.steps[-1]])
"
```
Expected: prints rewards (two finite numbers) and statuses (both `'DONE'` or `'INACTIVE'`). No `'ERROR'` status. No exceptions.

- [ ] **Step 4: G4 verdict**

If Step 3 passes: G4 PASSED. If anything errors: do NOT submit. Diagnose, fix, re-run from Step 1.

### Task 3.13: Handoff for submission

**Files:** none.

- [ ] **Step 1: Surface submission instructions to the user**

Tell the user verbatim:

```
G4 passed. v1 (heuristic baseline) is ready for submission.

Tarball: <absolute path to submission.tar.gz>
SHA-256: <hash printed by pack>

To submit:
  cd /home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars
  kaggle competitions submit orbit-wars -f submission.tar.gz -m "v1: heuristic baseline (orchestrated build 2026-04-30)"

After submitting, monitor with:
  kaggle competitions submissions orbit-wars

Worktrees can be removed after you commit the integrated codebase:
  git worktree remove .worktrees/c1-domain
  git worktree remove .worktrees/c2-rl
  git worktree remove .worktrees/c3-tooling

Want me to run the submit command for you, or will you handle git/submission yourself?
```

- [ ] **Step 2: Wait for user instruction on whether to submit and/or commit**

If user says "submit": run the kaggle command, capture the submission ID, surface it back. If user says "I'll handle it": stop here.

---

## Self-review (orchestrator's check before saving)

**1. Spec coverage:**
- §0 Purpose → covered by plan goal/architecture.
- §1 Goals/non-goals → enforced by C2 prompt ("do NOT train models in this session"), C3 part-2 prompt ("never crash, never time out"), and the v1 quality bar in Task 3.8 Step 6.
- §2 Operating context → embedded in every coder prompt as `READ FIRST` references.
- §3 Agent roster → 9 explorers in Task 1.2; orchestrator-only Phase 2; 3 coders in Tasks 3.2/3.3/3.6/3.7.
- §4 Phase gates → G1 (Task 1.3), G2 (Task 2.3), G3 (Task 3.4), G4 (Task 3.12).
- §5 File tree → File Structure table at top maps every file to a task.
- §6 Submission packaging → C3 part-2 prompt + Task 3.12 verification.
- §7 v1 heuristic → C3 part-2 prompt enumerates all components and references spec §7.2 constants by name.
- §8 RL scaffold → C2 prompt enumerates all modules and references spec §8 hyperparams.
- §9 Iteration roadmap → not in this plan (it's the post-v1 plan; out of scope per "this plan produces v1").
- §10 Risks → mitigations are baked into prompts (param cap, parity tests, defensive `agent` boundary).
- §11 Open questions → no plan needed; deferred to coders' judgment within their scopes.
- §12 Git policy → Operating ground rules at top + every coder prompt.
- §13 Approval → recorded.

**2. Placeholder scan:** No "TBD", no "TODO" (only as content described in CLI command stubs that C3 part-2 *replaces*), no "implement later", every prompt has actual content, every verification command has actual flags. Code blocks present where shown. ✓

**3. Type consistency:** Function/class names match between sub-agent prompts and verification steps:
- `OrbitWarsSim` (C1) referenced in C2's env.py prompt. ✓
- `HeuristicConfig` (C3 part-2) referenced consistently. ✓
- `agent` is the public name in `main.py` and `orbit_wars.heuristic.strategy`. ✓
- `score_target`, `ships_needed`, `safe_angle`, `incoming_threats_for`, `defense_priority`, `comet_capture_priority` — all referenced consistently in C3 part-2 prompt and spec §3.3 + §7.2. ✓
- `predict_planet_position` (C1) — single name throughout. ✓
- `sun_segment_intersect` — same name in C1 prompt and C3 part-2's pathing usage. ✓
- `build_policy` referenced in Task 3.8 Step 2 verification — C2 prompt does NOT explicitly require this name. **Mitigation:** add a note in C2 prompt that the policy module must export a `build_policy()` factory for orchestrator verification. (Fixed inline below.)

**4. Gates land software:** every gate (G1–G4) has explicit pass criteria and a "block on failure" instruction.

Issue found: C2 prompt didn't specify the `build_policy()` factory name that the orchestrator verifies in Task 3.8 Step 2. Fixing inline.
