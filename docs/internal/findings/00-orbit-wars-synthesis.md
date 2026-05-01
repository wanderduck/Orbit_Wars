# Orbit Wars — Integrated Findings & Adoption Plan (Phase 2 synthesis brief)

**Date:** 2026-04-30
**Inputs:** `docs/internal/findings/E1..E9-*.md` (9 explorer reports)
**Status:** Awaiting G2 user review

---

## ⚠️ Top-line finding (read first)

The leaderboard data inverts our prior assumption. Among the 5 reference notebooks pulled:

| Notebook | Approach | Reported LB Score |
|----------|----------|-------------------|
| E5 — bovard / getting-started | Heuristic (sniper baseline) | n/a (tutorial) |
| E6 — pilkwang / structured-baseline (v11) | **Heuristic** (5-layer pipeline) | n/a (no LB cited) |
| E7 — kashiwaba / RL tutorial | **PPO RL** (tutorial scaffold) | **n/a (tutorial, no LB)** |
| E8 — sigmaborov / lb-958-1-...-reinforce | **Heuristic** (E6 lineage v6, +REINFORCE missions) | **958.1** |
| **E9 — romantamrazov / lb-max-1224** | **Heuristic** (E6 lineage, further tuned) | **1224 ← highest known** |

**The two highest-scoring reference agents are pure heuristics, not RL.** "REINFORCE" in E8/E9's slugs refers to the **REINFORCE-mission strategy primitive** (a defensive tactic), NOT Williams' policy-gradient algorithm. The only true RL implementation in the reference set is E7, which is an officially-acknowledged tutorial without a leaderboard score, with simplified action design (target selection only — ship count and aiming are NOT learned, both inherited verbatim from the dumb sniper).

**Implication:** the spec's existing plan (Reading A: v1 ships heuristic, RL builds in parallel) is consistent with the evidence. But the spec's "RL-leaning" framing (Q4 in original brainstorming) over-weights RL relative to what the data supports. **Recommend re-balancing C2 (RL) and C3 (heuristic) effort allocation in favor of C3.** Specific recommendation in §5.A below.

---

## 1. Rules & Constraints Codex (from E1 + E2)

### Game-engine constants — **canonical reference for our codebase**

| Param | Value | Source |
|-------|-------|--------|
| Board | 100×100 continuous, origin top-left | E1 lines 85, 246 |
| Sun center | (50.0, 50.0) | E1 line 86 |
| `sunRadius` | 10.0 | E1 line 245 |
| `episodeSteps` | 500 | E1 line 242 |
| `actTimeout` | 1 second/turn | E1 line 243 |
| `shipSpeed` (max fleet speed) | 6.0 | E1 line 244 |
| `cometSpeed` | 4.0 units/turn | E1 line 247 |
| Fleet speed formula | `1.0 + (maxSpeed - 1.0) * (log(ships) / log(1000))^1.5` | E1 line 121 |
| Player IDs | 0-3 | E1 line 199 |
| Neutral owner sentinel | -1 | E1 line 93 |
| Planet radius | `1 + ln(production)` | E1 line 94 |
| Production range | integer 1-5 | E1 line 95 |
| Initial garrison range | 5-99 (skewed low) | E1 line 96 |
| Home planet starting ships | 10 | E1 line 107 |
| Orbiting condition | `orbital_radius + planet_radius < 50` | E1 line 100 |
| `ROTATION_RADIUS_LIMIT` | 50.0 (imported constant) | E3 line 165 |
| Angular velocity | 0.025-0.05 rad/turn (per-game randomized) | E1 line 100 |
| Planet count | 20-40 (5-10 symmetric groups of 4) | E1 line 103 |
| ≥3 static groups; ≥1 orbiting group | guaranteed | E1 line 103 |
| Comet radius | 1.0 (fixed) | E1 line 151 |
| Comet production | 1/turn when owned | E1 line 152 |
| Comet starting ships | min of 4 rolls from 1-99, shared across group | E1 line 153 |
| Comet spawn turns | 50, 150, 250, 350, 450 | E1 line 149 |
| Symmetry rule | `(x,y), (100-x,y), (x,100-y), (100-x,100-y)` | E1 line 87 |
| Skill init | μ₀ = 600, Gaussian N(μ, σ²) | E1 line 33 |

### Turn order (canonical, 7 phases)
1. Comet expiration → 2. Comet spawning → 3. Fleet launch → 4. Production → 5. Fleet movement (sun/planet/oob check) → 6. Planet rotation & comet movement (sweep into combat) → 7. Combat resolution.

### Combat resolution
1. Group arriving fleets by owner; sum same-owner ships.
2. Largest fights second-largest; difference survives.
3. Survivor: same owner as planet → reinforce garrison; different owner → fight garrison; if attackers > garrison, ownership flips.
4. **Two-attacker tie → all attacking ships destroyed (no survivors).**

### Submission constraints (legal)
- **NO INGRESS OR EGRESS during evaluation** (E2 §2.12) — no network calls, no remote weight loads, no LLM API at inference. All artifacts ship in the tarball.
- 5 submissions/day, 2 final submissions selectable (E2 §2.2).
- Final submission deadline: **2026-06-23**; ladder convergence ~2026-07-08.
- Winner license: **CC-BY 4.0** on submission AND source code (E2 §2.5).
- External data allowed but bounded by "Reasonableness Standard" (E2 §2.6); LLM API for offline development is OK; runtime LLM is not.
- Replays are public — opponents can study late-stage agents (E2 §2.11).
- **No Private Leaderboard** for Simulation competitions — final placement is public-leaderboard convergence (E2 §2.10).
- Score-magnitude does not affect skill update — optimize for narrow reliable wins (E1 line 39).
- Eligibility: 18+, not in sanctioned countries; Google/Kaggle employees can compete but cannot win (E2 §2.7, §3.1).

### Validation episode
On submit, the agent plays self-copies first (E2 §1.33). Failures mark Submission as "Error". **G4 (our pre-submission gate) MUST run a self-play smoke test that mirrors this.**

---

## 2. Game Mechanics & Agent Contract Codex (from E3 + E4)

### Agent contract
```python
def agent(obs):
    moves = []
    player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    planets = [Planet(*p) for p in raw_planets]
    # ...
    return moves  # list of [from_planet_id, angle_radians, num_ships]
```

- **Dual-mode `obs` access** — every observation field must be read with `obs.get(key, default) if isinstance(obs, dict) else obs.key` (E4 lines 235-236, also captured in CLAUDE.md). Failure to do this breaks the agent in either notebook or harness mode.
- **Named-tuple imports**: `from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet, CENTER, ROTATION_RADIUS_LIMIT` (E3 line 165, E4 line 237).
- **Action tuple**: `[from_planet_id, direction_angle_radians, num_ships]` — angle 0 = right, π/2 = down (E3 line 155).
- **Empty list `[]`** = no action (E3 line 158).

### Observation fields (all)
| Field | Type | Source |
|-------|------|--------|
| `planets` | `[[id, owner, x, y, radius, ships, production], ...]` (includes comets) | E3 line 137 |
| `fleets` | `[[id, owner, x, y, angle, from_planet_id, ships], ...]` | E3 line 138 |
| `player` | int (0-3) | E3 line 139 |
| `angular_velocity` | float (rad/turn, single global value per game) | E3 line 140 |
| `initial_planets` | same shape as planets, positions at game start | E3 line 141 |
| `comets` | `[{planet_ids, paths, path_index}, ...]` | E3 line 142 |
| `comet_planet_ids` | flat `[int, ...]` of planet IDs that are comets | E3 line 143 |
| `remainingOverageTime` | float (seconds) | E3 line 144 |

**Note (E4 vs E3 contract gap):** E4 only documents `player/planets/fleets/angular_velocity`. The full set lives in E3. Our `ObservationView` (C1's `state.py`) must surface ALL of them — agents need `initial_planets` for rotation prediction and `comets`/`comet_planet_ids` for comet logic.

### Local development workflow (E4)
```python
from kaggle_environments import make
env = make("orbit_wars", debug=True)
env.run(["main.py", "random"])        # 2-player vs random baseline
env.run(["main.py"] * 4)              # 4-player FFA self-play
env.run(["main.py"] * 2)              # what Kaggle runs as validation episode
final = env.steps[-1]
for i, s in enumerate(final): print(f"Player {i}: reward={s.reward}, status={s.status}")
```

### Submission packaging (E4 lines 310-330)
- `main.py` at bundle root, exposes `agent` function.
- Single-file: `kaggle competitions submit orbit-wars -f main.py -m "..."`.
- Multi-file: tar.gz with `main.py` at root.
- Notebook submit: `-k user/kernel -f submission.tar.gz -v 1 -m "..."`.

### Monitor / replay / logs (E4 lines 333-380)
```bash
kaggle competitions submissions orbit-wars
kaggle competitions episodes <SUBMISSION_ID> [-v]
kaggle competitions replay <EPISODE_ID> [-p ./replays]
kaggle competitions logs <EPISODE_ID> <agent_index>  # 0,1 (or 0..3 in 4P)
kaggle competitions leaderboard orbit-wars -s
```

---

## 3. Cross-Notebook Pattern Table (from E5-E9)

Patterns observed across the 5 reference notebooks. ✓ = adopt verbatim or close to it; ◇ = present but variant; ✗ = absent or weak; ☆ = key insight.

| Pattern / Technique | E5 bovard | E6 pilkwang | E7 kashiwaba | E8 sigmaborov | E9 romantamrazov |
|---------------------|-----------|-------------|--------------|---------------|------------------|
| **Approach class** | Heuristic-sniper | Heuristic-structured | RL (PPO) | Heuristic-structured (E6 lineage) | Heuristic-structured (E6 lineage) |
| Reported LB score | n/a | n/a | n/a | 958.1 | **1224** |
| Dual-mode `obs` access | ✓ | ✓ | ✓ | ✓ | ✓ |
| Named-tuple state (`Planet/Fleet`) | ✓ | ✓ (`namedtuple`) | ✓ (`PlanetState` dataclass) | ✓ | ✓ |
| Sun-segment-intersect | ✗ | ✓ ☆ `point_to_segment_distance` | ✓ `shot_crosses_sun` | ✓ (E6) | ✓ (E6) |
| Logarithmic fleet-speed model | ✗ | ✓ `fleet_speed(ships)` | ✗ (uses fixed ship count) | ✓ | ✓ |
| Fleet sizing rule | `max(target.ships+1, 20)` floor | Per-target adaptive (`preferred_send`) | Same as bovard (fixed) | Per-target adaptive | Per-target adaptive |
| Arrival-time ownership forecast | ✗ | ✓ ☆ `min_ships_to_own_at` | ✗ | ✓ | ✓ |
| Same-turn combat resolver matching env | ✗ | ✓ ☆ `resolve_arrival_event` | ✗ | ✓ | ✓ |
| Planet-rotation prediction | ✗ | ✓ `predict_target_position` | ◇ via `is_rotating` flag only | ✓ | ✓ |
| Iterative size↔ETA settlement (`settle_plan`) | ✗ | ✓ ☆ | ✗ | ✓ | ✓ |
| 5-iteration intercept solver | ✗ | ✓ `aim_with_prediction` | ✗ | ✓ | ✓ |
| Mission decomposition (capture/snipe/swarm/reinforce/recapture/crash) | ✗ | ✓ all | ✗ (action = target only) | ✓ + REINFORCE explicit | ✓ + REINFORCE explicit |
| 4-player crash exploit | ✗ | ✓ `detect_enemy_crashes` | ✗ | ◇ (likely yes — same constants) | ✓ |
| Reaction-time gating (my_eta vs enemy_eta) | ✗ | ✓ ☆ | ✗ | ✓ | ✓ |
| Domination-mode value adjustments | ✗ | ✓ (5–8% multipliers) | ✗ | ✓ | ✓ |
| Indirect-wealth feature | ✗ | ✓ neighbor F/N/E weights 0.35/0.9/1.25 | ◇ via global features | ✓ | ✓ |
| Doomed-evac salvage | ✗ | ✓ | ✗ | ✓ | ✓ |
| `TOTAL_WAR_REMAINING_TURNS` endgame trigger | ✗ | (likely) | ✗ | (likely) | ✓ **= 55, was 38** ☆ |
| Time-budget gating (`SOFT_ACT_DEADLINE`) | ✗ | ✓ | ✗ | ✓ | ✓ |
| PPO algorithm | ✗ | ✗ | ✓ | ✗ | ✗ |
| Self-play opponent | ✗ | (uses env-side opponent) | ✓ snapshot-sync | ✗ | ✗ |
| TrueSkill/league matchmaking | ✗ | ✗ | ✗ | ✗ | ✗ |
| Per-planet decision factoring | (one-loop-per-planet) | (mission-loop) | ✓ ☆ (each planet = independent decision) | (mission-loop) | (mission-loop) |
| 3-encoder feature decomposition (self/global/candidate) | ✗ | ✗ | ✓ ☆ | ✗ | ✗ |
| K-nearest candidate gating | ✗ | (top-K via reaction-time) | ✓ `candidate_count = 8` | (top-K via reaction-time) | (top-K via reaction-time) |
| Audit-trail tuning comments (`# was X`) | ✗ | ✗ | ✗ | ✗ | ✓ ☆ |

---

## 4. Adoption decisions

Mapped to coders C1, C2, C3 per spec §3.3. Verdict legend: **adopt v1** = lift into v1 codebase; **defer v2+** = build infra but not in v1; **skip** = do not invest.

### Heuristic mechanics — adopt v1, mostly C1 + C3

| Item | Source | Verdict | Owner |
|------|--------|---------|-------|
| Dual-mode `obs` access wrapper | E4, E5, E6 | **adopt v1** (per spec §2 already) | C1 (`state.py`) |
| Named-tuple `Planet/Fleet` import + splat | E3, E4 | **adopt v1** | C1 |
| `fleet_speed(ships)` log curve | E1 line 121, E6 cell 7 | **adopt v1** | C1 (`geometry.py`) |
| `point_to_segment_distance` + sun-collision check | E6 cell 7 | **adopt v1** ☆ | C1 (`geometry.py`) |
| `safe_angle_and_distance` with sun deflection fallback | E6 | **adopt v1** | C1 (`geometry.py`) |
| `predict_planet_position` (rotation) | E1 line 100, E6 | **adopt v1** | C1 (`rotation.py`) |
| Comet path lookahead via `paths`+`path_index` | E1 line 159 | **adopt v1** | C1 (`state.py` exposes; heuristic uses) |
| `simulate_planet_timeline` over HORIZON | E6, E8, E9 | **adopt v1** ☆ | C1 (`sim.py` for RL parity AND heuristic forecast) |
| `resolve_arrival_event` — same-turn combat | E6 cell 8 | **adopt v1, verbatim** ☆ | C1 |
| `WorldModel.min_ships_to_own_by` — exact arrival-time need | E6 cell 8 | **adopt v1** ☆ | C1 |
| `WorldModel.reinforcement_needed_to_hold_until` | E9 | **adopt v1** (over E8's narrower variant) | C1 |
| `aim_with_prediction` (5-iter intercept + sun fallback) | E6 cell 7 | **adopt v1** ☆ | C1 (`geometry.py`) |
| `settle_plan` size↔ETA iterative settlement | E6 cell 9 | **adopt v1** | C3 (`heuristic/sizing.py`) |
| Mission decomposition (capture/snipe/swarm/reinforce/recapture/crash) | E6, E8, E9 | **adopt v1, lean** (capture+snipe+reinforce+sun-aware pathing for v1; swarm+crash+recapture for v1.1) | C3 |
| `target_value` master scoring | E6 cell 9 | **adopt v1** (full version) | C3 (`heuristic/targeting.py`) |
| `preferred_send` adaptive sizing with margins | E6 cell 9 | **adopt v1** | C3 (`heuristic/sizing.py`) |
| `opening_filter` reaction-time-gated | E6 | **adopt v1** | C3 |
| `detect_enemy_crashes` (4P) | E6 cell 9 | **adopt v1** (cheap, free 4P wins) | C3 (`heuristic/comets.py` or sibling) |
| Domination-mode flags (`is_behind/is_ahead/is_finishing/is_dominating`) | E6 | **adopt v1** | C3 |
| `proactive_keep` reserve from top-3 enemies | E6 | **adopt v1** | C3 (`heuristic/threats.py`) |
| Doomed-evac salvage | E6 | **adopt v1** | C3 |
| `TOTAL_WAR_REMAINING_TURNS = 55` endgame trigger | E9 ☆ | **adopt v1** | C3 (`heuristic/config.py` constant) |
| `SOFT_ACT_DEADLINE = 0.82` time budget gate | E6 | **adopt v1** ☆ (TLE insurance) | C3 |
| `# was X` audit-trail comment convention | E9 | **adopt v1** | C3 (`heuristic/config.py`) |
| Indirect-wealth feature (neighbor F/N/E sum) | E6 | **adopt v1** | C3 (`heuristic/targeting.py`) |
| Full E6 constants table (D_REF, weights, multipliers, ~80 entries) | E6 cells 6+9 | **adopt v1** as starting values for `HeuristicConfig` (override spec §7.2's tentative values where E6 differs — log differences in `# was` comments) | C3 |

### RL infrastructure — defer v2+, build scaffold, lower priority

| Item | Source | Verdict | Owner |
|------|--------|---------|-------|
| Per-planet decision factoring | E7 | **adopt for C2 scaffold** ☆ | C2 (`policy.py`) |
| 3-encoder MLP (self+global+candidate) | E7 cell 14 | **adopt for C2 v1 scaffold** (upgrade to set transformer if/when needed) | C2 |
| K-nearest candidate gating (`candidate_count=8`) | E7 cell 9 | **adopt for C2** | C2 (`env.py`) |
| `safe_target_logits` mask-and-softmax fallback | E7 cell 15 | **adopt for C2** | C2 |
| Snapshot self-play with periodic sync | E7 cell 16 | **build, but UPGRADE to TrueSkill league** per spec §8.4 | C2 |
| YAML+dataclass config pattern | E7 cells 9, 11 | **adopt for C2** (tuning sweep readiness) | C2 |
| GAE | (not in E7) | **add in C2** (E7 uses MC returns; high variance over 500-step episodes) | C2 |
| Sparse terminal reward | (E7 default) | **adopt initially**, gate shaped reward behind flag | C2 |
| Default PPO hyperparams (lr=3e-4, gamma=0.99, etc.) | E7 cell 11 | **adopt as starting point** but spec §8.4 has slightly different (gamma=0.997, n_epochs=6) — start with E7 for parity, sweep | C2 |

### Skip in v1 (low ROI given evidence)

| Item | Reason |
|------|--------|
| Investment of v1 effort in RL beyond scaffold | Top-of-leaderboard reference is heuristic; RL tutorial has no LB score; ROI per dev-hour favors heuristic tuning |
| Image-based observations | E7 confirms scalar features sufficient; image-based untested in any reference |
| Discretized angle/ship action heads in v1 | E7 doesn't use them; build for v2 RL only |
| Modal compute for v1 | Local 2080 Ti suffices for the small policy in C2; revisit at week 3 |

---

## 5. Actionable recommendations (prioritized)

### 5.A. **Critical (orchestrator-level): rebalance C2/C3 effort allocation** — REQUIRES USER DECISION

The leaderboard data argues we should spend less time on C2 (RL) and more on C3 (heuristic). The spec §3.3 already names this — C3 builds the v1 ship and C2 builds infrastructure for v2+ — but the **emphasis** matters:

**Two paths to choose between:**

- **Path A (proceed as-specced):** C2 builds the full RL scaffold per spec §8 (PlanetPolicy + env + PPO + league + remote.py). C3 builds the v1 heuristic per spec §7. Both run in parallel as Tier 2.
- **Path B (rebalance toward heuristic):** Compress C2's scope to a **deferred RL stub** (just the file scaffolding + a TODO that says "build when we revisit RL post-v1"). Move that effort to C3 to build a **richer heuristic** — the full E6 mission set including swarm, recapture, crash-exploit, and the `WorldModel.simulate_planet_timeline` arrival-forecast precomputation. This means a stronger v1 at the cost of zero RL infrastructure for now.

**My recommendation: Path A but with reduced expectations of C2.** Build the RL scaffold (it's option value; cheap to keep dormant later) but reduce the eval-gate ambition (don't promise we'll train an RL model that beats the heuristic in v2 — make it conditional on the heuristic plateauing first). This matches the spec's existing direction without the inflated RL framing.

Surfacing this for explicit user decision at G2.

### 5.B. **Adopt E6 wholesale as the v1 heuristic foundation**

C3's spec §7 components map almost 1:1 onto E6's modules. Don't reinvent — lift E6's `target_value`, `preferred_send`, `aim_with_prediction`, `resolve_arrival_event`, `min_ships_to_own_by`, `detect_enemy_crashes`, `simulate_planet_timeline` directly. Update spec §7.2's tentative constants to E6's measured values.

Specifically: replace the tentative `D_REF=30`, `SUN_PENALTY=1`, etc. in spec §7.2 with E6's measured values (`SUN_R = 10.0`, `SUN_SAFETY = 1.5`, the full constants table from E6 cells 6+9). Use E9's `TOTAL_WAR_REMAINING_TURNS = 55` and E8's REINFORCE constants. Preserve the `# was X` audit-trail convention.

### 5.C. **C1 must build `simulate_planet_timeline` and `WorldModel`**

The spec §3.3 only mentions `state.py`, `geometry.py`, `rotation.py`, `sim.py`. But the heuristic in E6/E8/E9 leans heavily on a **WorldModel** that precomputes `simulate_planet_timeline` over `HORIZON=110` and supports `min_ships_to_own_by` / `reinforcement_needed_to_hold_until` queries. C1 must add this — it's not just for RL, it's the substrate for the heuristic too.

Suggested addition to C1's deliverables: `src/orbit_wars/world.py` containing `WorldModel`, `simulate_planet_timeline`, `resolve_arrival_event`, `min_ships_to_own_by`, `reinforcement_needed_to_hold_until`. Alternatively rename `sim.py` to `world.py` and host these methods there.

### 5.D. **Drop the home-rolled `OrbitWarsSim` for parity in v1; rely on `kaggle_environments` directly**

Spec §8.1 says C1 builds a fast Python sim mirroring `kaggle_environments` for RL rollouts. **For v1 (heuristic-only), this is unnecessary effort.** The `WorldModel.simulate_planet_timeline` is enough for the heuristic's forecasts. The home-rolled `OrbitWarsSim` is only needed for fast RL rollouts, which is a v2+ concern.

Recommend: C1 builds `WorldModel` (heuristic substrate). C2 builds `OrbitWarsSim` only when actually starting RL training (post-v1). This trims Tier 1 work and accelerates v1 ship.

### 5.E. **C3 part-1 must add specific deps**

Per E7 the RL scaffold needs `torch` (already in pyproject.toml), `pyyaml` (NOT in pyproject.toml currently — confirmed from C3-part-1's grep target). Add `pyyaml` to deps. C2's training config will use it.

Plus the spec's already-listed: `kaggle-environments`, `gymnasium`, `pytest`, `pytest-cov`, `ruff`, `mypy`/`ty`, `typer[all]`, `rich`, `hypothesis`, optional `modal`.

### 5.F. **Adopt the audit-trail tuning convention in code**

E9's `TOTAL_WAR_REMAINING_TURNS = 55     # was 38 — endgame push starts sooner` style is uniquely valuable. Embed it in C3's `HeuristicConfig`. Each tuning sweep updates the constant AND adds a `# was X — context` comment. Eight weeks of tuning becomes a self-documenting changelog.

### 5.G. **Reserve a "submission cadence" decision for after v1 ships**

5 submissions/day is generous. Validation episode delays before bots join the pool (E2 §1.33). Recommend: ship v1 once, then HOLD further submissions until we have a v1.1 with a measured improvement vs v1 in local self-play, rather than burning daily slots on minor tweaks. Save submission slots for substantial deltas.

### 5.H. **Track competitor strategy via replays**

Replays are public (E2 §2.11). Plan: at week-3 (after we're on the leaderboard), download top-50 replays via `kaggle competitions replay`, analyze any unusual patterns. Don't do this until we have a baseline to compare against.

### 5.I. **Use submitting-as-self-test discipline**

`env.run([main.py, main.py])` mirrors Kaggle's validation episode. **G4 must run this exact pattern, in a fresh tmpdir from the extracted tarball, to catch any "imports fine in dev but breaks in submission" issues.**

---

## 6. Updates to spec §7.2 constants

Recommend overriding spec §7.2's tentative constants with E6's measured values. Net effect:

| Spec §7.2 | Tentative | E6 measured | Adopt |
|-----------|-----------|-------------|-------|
| `SUN_RADIUS` | 10.0 | 10.0 (`SUN_R`) + safety 1.5 | E6's: 10.0 + `SUN_SAFETY = 1.5` |
| `D_REF` | 30.0 (≈board/3) | (not in E6 directly — distance enters via `target_value`'s `(send + turns*cost_w + 1)` denominator) | Drop `D_REF`; use E6's `value / (send + turns*cost_w + 1)` denominator pattern |
| `SUN_PENALTY` | 1.0 | n/a — sun-blocked shots are fully rejected, not penalty-scored | Drop `SUN_PENALTY`; use sun-segment-intersect to mask/route, not penalize |
| `COMET_BONUS` | 0.5 | (E6 `COMET_VALUE_MULT = 0.65` — applied to whole value) | Use E6's: `COMET_VALUE_MULT = 0.65` |
| `COMET_LIFETIME_REF` | 100 | Comet lifetime cap is via `comet_remaining_life`; max chase 10 turns | Use E6's `COMET_MAX_CHASE_TURNS = 10` and intercept-time cap |
| `w_roi` / `w_dist` / `w_prod` | 1.0 / 0.5 / 0.3 | E6 doesn't use a 3-weight linear blend; uses `value` (quality) divided by `(send + turns*cost_w + 1)` (cost) | Replace tentative `w_*` blend with E6's value/cost ratio + score-multipliers |
| `SAFETY_MARGIN` | 2 | `REINFORCE_SAFETY_MARGIN = 2`, plus per-mission margins | Use E6's per-mission (`NEUTRAL_MARGIN_BASE = 2`, `HOSTILE_MARGIN_BASE = 3`, etc.) |
| `HOME_RESERVE` | 5 | E6 uses dynamic `proactive_keep` (top-3 enemies × 18%) + `keep_needed` from world model | Replace with E6's `proactive_keep` |
| `MIN_LAUNCH` | 3 | E6 uses `PARTIAL_SOURCE_MIN_SHIPS = 6` for partial-source missions | Use E6's threshold |
| `DEFENSE_BUFFER` | 2 | `DEFENSE_SEND_MARGIN_BASE = 1` + `DEFENSE_SEND_MARGIN_PROD_WEIGHT = 1` (mult by production) | Use E6's |
| `COMET_ROI_THRESHOLD` | 0.05 | E6: comets handled via `COMET_VALUE_MULT = 0.65` and `COMET_MARGIN_RELIEF = 6` rather than a hard threshold | Replace with E6's design |

The spec's tentative values were placeholders before the data arrived. The E6 measured values are the new starting points.

### Spec §3.3 C1 deliverable updates (recommend)

Add to C1:
- `src/orbit_wars/world.py` — `WorldModel`, `simulate_planet_timeline`, `resolve_arrival_event`, `min_ships_to_own_by`, `reinforcement_needed_to_hold_until`. (Alternatively rename `sim.py` to host these.)

Defer/conditional:
- `src/orbit_wars/sim.py` (the gymnasium-parity simulator) — only needed when C2 starts actual RL training. Move from Tier 1 to Tier 2 with C2.

### Spec §3.3 C3 part-2 deliverable updates (recommend)

Adopt E6's `mission` decomposition explicitly:
- `src/orbit_wars/heuristic/missions/capture.py`
- `src/orbit_wars/heuristic/missions/snipe.py`
- `src/orbit_wars/heuristic/missions/reinforce.py`
- `src/orbit_wars/heuristic/missions/recapture.py` (v1.1)
- `src/orbit_wars/heuristic/missions/swarm.py` (v1.1)
- `src/orbit_wars/heuristic/missions/crash_exploit.py` (v1.1; 4P only)

For v1 ship: capture + snipe + reinforce + sun-aware pathing + threats. v1.1 adds swarm + recapture + crash-exploit.

---

## 7. Open questions surfaced (from individual reports)

These don't block Phase 3 but should be tracked:

- **Combat tie behavior with 3+ attackers** (E1 / E3 open question): rule is ambiguous when 3+ attackers of distinct sizes engage. C1's parity tests should probe this against `kaggle_environments` ground truth.
- **Comet starting-ship distribution** ("min of 4 rolls" — uniform integer? Bernoulli? Something else?): C1's tests with seeds should expose the distribution shape.
- **`remainingOverageTime` semantics** (E1, E3): not described in docs. Empirical test required.
- **Production timing on freshly captured planets** (E3): logically, ownership flips in phase 7 after production in phase 4 — verified by reading code OR by C1 parity test.
- **2P vs 4P ID conventions**: docs say 0-3, but 2P uses {0,1}? Empirical via `env.run([main.py, "random"])`.
- **Action validation behavior** when over-budget / wrong owner / NaN angle: drop / clamp / error? C1 should test.
- **Diff between E6, E8, E9** to confirm which constants moved most. `diff` between extracted .py files would expose this — useful for late-stage tuning sweeps.
- **`remainingOverageTime` budget size** — empirical test will tell.
- **Whether Kaggle's runtime drift breaks the env-version assumed by `kaggle-environments` PyPI** (E2 / E3 open question). C1's parity test catches deviation early.

---

## 8. Proposed action — pause for G2 user review

This brief surfaces one critical orchestrator-level decision (§5.A: rebalance C2/C3 effort) and several smaller spec amendments (§6). I recommend the user reads §0 and §5 specifically, then either:

- **(a) approves Path A (proceed as-specced)** → I move to Phase 3 Tier 1 (C1 + C3 part-1 dispatch).
- **(b) approves Path B (compress C2)** → I revise the spec §3.3 inline to compress C2's scope, then move to Phase 3.
- **(c) requests other revisions** → I make them and re-surface.

Submission deadline 2026-06-23 — we have ~8 weeks. Phase 3 Tier 1 is ready to begin once G2 passes.
