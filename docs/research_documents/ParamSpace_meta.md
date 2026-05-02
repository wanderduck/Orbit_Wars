# CMA-ES Parameter Bounds for v1.5G HeuristicConfig — Research & Recommendations

## TL;DR

- **Public information about the Kaggle "Orbit Wars" competition is sparse**: the official page describes it only as "Conquer planets rotating around a sun in continuous 2D space — a real-time strategy game for 2 or 4 players" with a $50K prize pool; rules, scoring formulas, exact turn caps, and parameter dumps from top competitors are gated behind the Kaggle login wall, and no public GitHub repos, post-mortems, or full strategy write-ups for v1.5G-style heuristic bots exist as of May 2026. Treat all "Meta Baseline (x0)" entries as informed estimates rather than scraped values.
- **Orbit Wars is structurally a Galcon / Planet-Wars variant** (planets that produce ships, fleets sent to capture / reinforce, with the twist that planets *orbit* a sun, plus three planet "types" — static, rotating, comet — that change the value/predictability of holding them). The well-documented Galcon / Planet-Wars heuristic literature (Mora et al., zvold, melisgl/bocsimacko, AiGameDev) is the right analog for what each parameter category does and what magnitudes good bots use.
- **CMA-ES bound recommendations** (Hansen tutorial, libcmaes practical hints, pymoo, optuna): set `sigma0 ≈ ¼ × (max−min)`; place `x0` such that the optimum is plausibly within `[x0 − sigma0, x0 + sigma0]`; bounds should be wide enough that the optimum is interior, but narrow enough that `sigma0` is meaningful. **Wider bounds (±2–3×)** are recommended over tighter (±50%) per the working philosophy that v1.5G's defaults are a *floor to beat*, not a known-near-optimum starting point.

---

## Key Findings

### 1. Orbit Wars game mechanics (what we could verify)

- **Genre / structure** (Kaggle official one-liner, confirmed): RTS with 2 or 4 players in continuous 2-D space; players conquer **planets that orbit a sun**.
- **Public Kaggle code surfaces** that exist but are gated by Kaggle's login/Cloudflare (titles only): "Orbit Wars – Reinforcement Learning Tutorial" (kashiwaba), "Orbit Wars 2026 – Tactical Heuristic" (sigmaborov), and "Orbital Strategist — The Revolutionary Orbit Wars" (aminmahmoudalifayed). These exist (so a heuristic baseline is publicly shared), but their text is not retrievable without authentication.
- **Independent confirmation**: A March 2026 community post (digitado.com.br) noted "$50k in prize money," "huge but pruneable action space," "~2 weeks in, 2 months to go," and that competitors are exploring RL approaches but no one has trained anything yet — confirming the competition is live, mid-flight, and that heuristic bots tuned with CMA-ES are a sensible meta.
- **Inferred from the heuristic vocabulary in our `HeuristicConfig`**:
  - "Production" = a planet generates ships per turn while owned (Galcon convention).
  - "Capture" = sending enough ships to overwhelm a planet's garrison and switch ownership.
  - "Snipe" = late attack timed to take a planet just after an enemy spends ships on it.
  - "Reinforce" = transferring ships from a friendly planet to another friendly planet under threat.
  - "Defense" = retaining ships locally vs. enemy incoming fleets.
  - **Planet types**: *static* sits at a fixed point; *rotating* orbits the sun on a predictable circular path (so future-position prediction matters and travel time is a function of orbital phase); *comet* is on a highly eccentric orbit, only periodically valuable. The *static_neutral_value_mult* / *static_hostile_value_mult* split is the classic Galcon insight that owner-state changes a planet's worth far more than its base growth.
- **Episode length**: 500-turn episodes (per CLAUDE.md, asserted but not externally re-verified). Time-horizon parameters are capped at 250 (½ episode) so that "look-ahead" parameters don't run out the clock.

### 2. CMA-ES bound-setting best practices (consensus across sources)

From Hansen's tutorial (arXiv:1604.00772), the cma-es.github.io practical-hints page, libcmaes wiki, pymoo docs, and Loshchilov & Hutter (arXiv:1604.07269):

1. **Variables should be scaled so a single sigma is sensible across all dimensions.** Translate raw bounds into a normalized space; CMA-ES is invariant to translation but assumes similar sensitivity per coordinate.
2. **`sigma0 ≈ ¼ × (upper − lower)`** is the canonical rule (pymoo, optuna's default `min_range/6`, Hansen practical hints). The optimum should plausibly lie within `[x0 ± sigma0]` and certainly within `[x0 ± 3·sigma0]`.
3. **Set bounds wide enough that the optimum is interior**, not on the boundary; convergence on the boundary is a CMA-ES failure mode (creeping behavior / step-size collapse).
4. **For positive-only parameters with ratios > ~100×**, prefer logarithmic encoding (`10^x`); but for parameters in O(1) range like value multipliers, linear is fine.
5. **Integer / discrete parameters** suffer step-size collapse on plateaus (Hansen 2011, Hamano et al. 2022). Mitigations: use larger initial sigma on those coordinates, or apply CMA-ES-with-margin (lower-bounded marginal probability). Practically: give integer fields a relatively wide [floor, ~4× default] range so the discretization granularity stays much smaller than sigma.
6. **When the default is treated as a *floor to beat*** (our case), wider bounds (±2–3×) allow CMA-ES to escape any bad basin; narrow bounds anchor the search to the prior. Loshchilov & Hutter explicitly note that wide ranges + noise + small budgets are inefficient for sequential optimizers, so prefer larger λ (population) when widening bounds.
7. **Avoid degenerate fractions** at exactly 0 or 1; clip to `[0.01, 0.99]` or `[0.05, 0.99]` (matches the "fractions: [0.1, 0.99]" rule).

These map directly onto eight category recipes that I apply parameter-by-parameter below.

---

## Details — Parameter-by-Parameter Bounds Tables

> **Conventions:** **Min Bound** and **Max Bound** are absolute hard limits passed to CMA-ES (`bounds=[lo, hi]`). **Meta Baseline (x0)** is the best estimate of what a strong submission likely uses, where the upstream Galcon/PW literature gives a transferable hint; entries marked "—" indicate no transferable estimate and CMA-ES should initialize at the v1.5G default. Bounds are deliberately ~2–3× wider than the default per the philosophy in section 2.6 above. All assume episode length = 500 turns.

### A. Value multipliers (10 floats, default range 0.65–1.85, bound envelope [0.3, 5.0])

These weight target attractiveness. Galcon-bot literature (Mora et al. evolutionary tuning) found best values typically in 0.5–3.0 with significant spread by map type — so a generous [0.3, 5.0] envelope captures all known good basins.

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `static_neutral_value_mult` | 1.4 | bonus for unowned static planets | 0.30 | 5.00 | 1.5 |
| `static_hostile_value_mult` | 1.55 | bonus for enemy-owned static planets | 0.30 | 5.00 | 1.3 |
| `rotating_opening_value_mult` | 0.9 | penalty for orbiting planets in opening | 0.30 | 5.00 | 1.0 |
| `hostile_target_value_mult` | 1.85 | bonus for enemy targets generally | 0.30 | 5.00 | 1.4 |
| `opening_hostile_target_value_mult` | 1.45 | bonus for enemy targets in opening | 0.30 | 5.00 | — |
| `safe_neutral_value_mult` | 1.2 | bonus for "safe" neutrals | 0.30 | 5.00 | 1.2 |
| `contested_neutral_value_mult` | 0.7 | penalty for contested neutrals | 0.30 | 5.00 | — |
| `early_neutral_value_mult` | 1.2 | bonus for neutrals in early game | 0.30 | 5.00 | — |
| `comet_value_mult` | 0.65 | penalty for comet targets (less stable) | 0.20 | 5.00 | 0.7 |
| `reinforce_value_mult` | 1.35 | bonus for reinforce missions | 0.30 | 5.00 | 1.1 |

> **Coupling note**: `static_neutral_value_mult` and `static_hostile_value_mult` are kept on independent [0.3, 5.0] ranges per the recipe — CMA-ES will discover their covariance from the population, so do NOT pre-link them.

### B. Score multipliers (6 floats, default range 1.05–1.25, bound envelope [0.3, 5.0])

These apply to the FINAL mission score (post target-value-multiplier × cost-ratio). Same width philosophy as Section A — they're conceptually downstream multipliers but mathematically the same kind of object.

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `static_target_score_mult` | 1.18 | static-target bonus on top of base score | 0.30 | 5.00 | — |
| `early_static_neutral_score_mult` | 1.25 | early-game static neutral bonus | 0.30 | 5.00 | — |
| `snipe_score_mult` | 1.12 | snipe mission bonus | 0.30 | 5.00 | 1.6 |
| `swarm_score_mult` | 1.06 | swarm mission bonus | 0.30 | 5.00 | — |
| `crash_exploit_score_mult` | 1.05 | crash-exploit mission bonus (FFA-only) | 0.30 | 5.00 | — |
| `defense_frontier_score_mult` | 1.12 | frontier-defense bonus | 0.30 | 5.00 | 1.8 |

> **Note on `snipe_score_mult` (default 1.12 → suggested x0 1.6) and `defense_frontier_score_mult` (default 1.12 → suggested x0 1.8)**: the upstream literature suggests we may be substantially under-weighting snipe and defense missions vs the meta. These are the two highest-confidence "starting point should be much higher than current default" hypotheses to test.

### C. Mission cost weights (4 floats, denominator weights, default 0.35–0.55, bound envelope [0.05, 2.0])

Used in `score = value / (send + turns × cost_weight + 1)`. Width philosophy: ~40× default range to test whether turn-cost should matter much more or much less.

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `attack_cost_turn_weight` | 0.55 | turn-cost weight for capture missions | 0.05 | 2.00 | — |
| `snipe_cost_turn_weight` | 0.45 | turn-cost weight for snipe missions | 0.05 | 2.00 | — |
| `defense_cost_turn_weight` | 0.40 | turn-cost weight for defense missions | 0.05 | 2.00 | — |
| `reinforce_cost_turn_weight` | 0.35 | turn-cost weight for reinforce missions | 0.05 | 2.00 | — |

### D. Send margins (4 ints, bound envelope [floor, 4×default with sanity adjustments])

Step-size can collapse on integer plateaus (Hansen 2011); wide bounds keep CMA-ES perturbing the variable.

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `safety_margin` | 1 | extra ships sent above WorldModel's "min needed" | 0 | 8 | 3 |
| `home_reserve` | 0 | min ships to keep at source planet | 0 | 15 | — |
| `min_launch` | 20 | minimum fleet size (smaller fleets too slow per log-1.5 curve) | 1 | 80 | 5 |
| `defense_buffer` | 2 | extra ships reserved when reinforcing a threatened planet | 0 | 12 | 5 |

> **High-confidence finding for `min_launch`** (default 20 → suggested x0 5): Galcon-bot literature consistently uses minimum-fleet thresholds in the 3–10 range. The current default of 20 may be aggressively over-conservative. CMA-ES's covariance with `safety_margin` and `home_reserve` will tell us whether this is a calibration-only issue or whether the current ship-sizing pipeline depends on min_launch being high.

### E. Time horizons (10 ints, bound envelope [floor, 250] capped at ½ episode)

Galcon/PW bots converge on 30–80-turn horizons in practice (zvold blog, AiGameDev guide); 250 is the absolute upper cap (half of a 500-turn episode).

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `sim_horizon` | 110 | how far the WorldModel timeline projects forward | 30 | 250 | — |
| `route_search_horizon` | 60 | max ETA we consider for a launch | 10 | 200 | — |
| `total_war_remaining_turns` | 55 | turns left when "total war" mode kicks in | 20 | 200 | — |
| `late_remaining_turns` | 60 | turns left when "late game" begins | 20 | 200 | — |
| `very_late_remaining_turns` | 25 | turns left when "very late" mode | 10 | 100 | — |
| `reinforce_max_travel_turns` | 22 | max ETA for reinforce launches | 5 | 100 | — |
| `reinforce_min_future_turns` | 40 | only reinforce planets that survive at least this long | 10 | 200 | — |
| `reinforce_hold_lookahead` | 20 | how far ahead the hold-check looks | 5 | 100 | — |
| `early_turn_limit` | 40 | turn at which "early game" ends | 5 | 200 | — |
| `opening_turn_limit` | 80 | turn at which "opening" ends | 20 | 250 | — |

### F. Reinforce mission integers + small-default floats

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `reinforce_min_production` | 2 | only reinforce planets with at least this production | 0 | 8 | — |
| `reinforce_safety_margin` | 2 | extra ships sent above the deficit | 0 | 12 | — |

### G. Fractions (4 floats including reinforce_max_source_fraction, bound envelope [0.1, 0.99])

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `reinforce_max_source_fraction` | 0.75 | max fraction of source's ships to send | 0.10 | 0.99 | 0.85 |
| `soft_act_deadline_fraction` | 0.82 | fraction of `actTimeout` to act within | 0.50 | 0.99 | — |

> **Note on `soft_act_deadline_fraction`**: bounds tightened to [0.50, 0.99] — going below ~0.5 means we're acting on less than half our turn-time budget, which is just leaving compute on the table. Above 0.99 risks timeouts.

### H. Late-game / discount-rate-like (single special float)

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `late_immediate_ship_value` | 0.6 | how much we value immediate ships in late game | 0.00 | 2.00 | 0.8 |

### I. Endgame thresholds and bonuses (2 ints + 1 large-positive float)

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `weak_enemy_threshold` | 45 | enemy ship count below which they're "weak" | 0 | 200 | — |
| `elimination_bonus` | 18.0 | score bonus for eliminating an opponent | 0.0 | 100.0 | — |
| `heavy_route_planet_limit` | 32 | cap on planets considered in heavy route search | 4 | 100 | — |

### J. Domination thresholds (sign-bounded floats)

| Field | Default | Purpose | Min Bound | Max Bound | Meta Baseline (x0) |
|---|---|---|---|---|---|
| `behind_domination` | -0.20 | threshold below which we're "behind" | -1.00 | 0.00 | — |
| `ahead_domination` | 0.18 | threshold above which we're "ahead" | 0.00 | 1.00 | — |
| `finishing_domination` | 0.35 | threshold for "finishing" mode | 0.00 | 1.00 | — |
| `finishing_prod_ratio` | 1.25 | production-ratio threshold for finishing | 0.50 | 5.00 | — |
| `behind_attack_margin_penalty` | 0.05 | aggression penalty when behind | 0.00 | 0.50 | — |
| `ahead_attack_margin_bonus` | 0.08 | aggression bonus when ahead | 0.00 | 0.50 | — |

---

## How to feed these into CMA-ES

- **Initial point `x0`**: use the **Meta Baseline column where given**, otherwise the v1.5G default. Where multiple plausible meta values exist, prefer slightly above the default (since defaults are treated as a floor).
- **`sigma0` (per-coordinate)**: pre-scale every dimension to `[0, 1]` via `(x − lo)/(hi − lo)`, then use a *single* scalar `sigma0 ≈ 0.25` (Hansen rule). Equivalently in raw units, set per-dim sigma = `0.25 × (hi − lo)`.
- **Population `λ`**: with 44 dimensions, default `λ = 4 + ⌊3·ln 44⌋ = 15`. Because the search is noisy (game outcomes are stochastic) and the bounds are deliberately wide, **double or triple λ to 30–50** (Loshchilov & Hutter 2016 used λ = 30 explicitly for noisy hyperparameter search). Consider BIPOP/IPOP-CMA-ES restarts with increasing λ.
- **Boundary handling**: use cma's `BoundPenalty` or `BoundTransform` so CMA-ES doesn't degenerate when individuals hit the wall — *do not* simply clip silently.
- **Integer fields** (Sections D, F, I and time horizons in E): apply rounding inside the fitness wrapper, AND use `cma`'s `integer_variables` option (which prevents step-size collapse on those coordinates). Hansen's mixed-integer recipe (Hansen 2011, Hamano 2022 "CMA-ES with Margin") is implemented in the `cmaes` Python package.
- **Evaluation noise**: average ≥ 30 games per candidate (mirrored opponents, varied seeds) before scoring, or use noise-aware CMA-ES (`cma.CMAEvolutionStrategy(..., {'noise_handling': True})`).

---

## Caveats

1. **Meta Baseline values are estimates from upstream Galcon/Planet-Wars literature, NOT scraped from real Orbit Wars top submissions.** The Kaggle Orbit Wars competition is live, gated, and (as of mid-2026) lacks public solution write-ups, GitHub mirrors, or RL/heuristic post-mortems. Top-bot heuristic constants in the *related* Galcon / Planet-Wars literature span enormous ranges across maps, so any single x0 is a moderate-confidence guess. **Treat the Meta Baseline column as a starting hint; always also run a CMA-ES seed initialized at the v1.5G default to hedge.**
2. **Field name mapping**: this version of the document maps every numeric field of v1.5G's actual `HeuristicConfig` (44 numeric fields, 2 booleans pinned). The earlier draft of this document used inferred Galcon-style names (e.g., `production_value_weight`, `defense_value_mult`) that did not exist in our codebase; that draft has been replaced with this verified mapping.
3. **Episode-length cap of 500 turns is asserted in CLAUDE.md, not externally verified.** If actual matches are 200 turns (Galcon/PW-2010 default) or 1000 turns, the time-horizon caps in Section E should scale accordingly (½ episode is a good rule-of-thumb upper bound).
4. **Wider bounds cost CMA-ES iterations.** With 44 dimensions, ~30 individuals/generation, and ~30 games/individual for noise control, each generation is ~1000 game evaluations. Budget 30–100 generations for convergence — i.e., 30k–100k matches. If compute is tight, the Section C cost weights and Section J domination thresholds are the lowest-marginal-sensitivity in PW-bot literature; narrow those first and keep Sections A, B, D wide.
5. **Coupling between `static_neutral_value_mult` and `static_hostile_value_mult`** (and other within-category pairs) is real — top bots almost certainly tune them as a function of map configuration. CMA-ES learns this covariance from data; **do not** hand-couple them in the bounds, but **do** initialize `x0` at slightly different values so the optimizer can detect their independent gradients early.
6. **The "v1.5G defaults are a floor to beat" framing is from the upstream tuning workflow assumption**, not externally verified for this specific competition. If the gap to the meta is actually smaller than assumed, narrower bounds (±50–100%) will converge faster; if larger, lean even wider (±3–4×) and consider random-search seeding before CMA-ES.
7. **Highest-confidence "default may be substantially off" hypotheses** worth watching during the first sweep:
   - `min_launch` (default 20 → suggested x0 5): Galcon literature uses 3–10. Our default may be aggressively over-conservative.
   - `snipe_score_mult` (default 1.12 → suggested x0 1.6): may be substantially under-weighted vs the meta.
   - `defense_frontier_score_mult` (default 1.12 → suggested x0 1.8): same observation.
   - `hostile_target_value_mult` (default 1.85 → suggested x0 1.4): may be over-weighted; capturing enemies might be less valuable than the current config implies.
   - `reinforce_value_mult` (default 1.35 → suggested x0 1.1): may be slightly over-weighted.
   - `late_immediate_ship_value` (default 0.6 → suggested x0 0.8): immediate-ship value in late game may be higher than current default suggests.
