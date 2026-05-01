# Heuristic Algorithm Research — Integrated Findings

**Date:** 2026-04-30
**Sources:** 8 research artifacts (4 PDFs, 1 research markdown, 3 web articles); per-source reports in `findings/R1-R8-*.md`
**Goal:** Distill the research into actionable improvements for `src/orbit_wars/heuristic/` so we can stop losing 70-90% to random.

---

## Per-source relevance ranking

| ID | Source | Type | Relevance | One-line takeaway |
|----|--------|------|-----------|-------------------|
| **R6** | primaryobjects — Isolation game heuristics with minimax | Blog + GitHub repo | **4 / 5** | Asymmetric weighting (`2*mine - theirs`), phase-aware switching, depth-dominates-heuristic |
| **R8** | securview — Heuristic threat detection | Vendor blog (URL not retrievable; sibling pages used) | **4 / 5** | Additive multi-feature threat score; tiered response thresholds; FP/FN asymmetry |
| **R5** | Comprehensive Research Report on Heuristic Algorithms (local MD) | Survey essay | **3 / 5** | A* `f=g+h` with admissibility; loss-avoidance asymmetry; selfish-routing as Tragedy-of-Commons in 4P |
| **R7** | datature — Object tracking algorithms 2025 | CV blog (URL denied; siblings used) | 2 / 5 | **Hungarian assignment** for fleet→target dispatch; predict-then-decide pattern |
| **R2** | heur1.pdf — Connect-4 minimax heuristics (Kang et al. 2019) | Journal article | 2 / 5 | Multi-tier value separation by orders of magnitude; ablation tournaments |
| **R4** | heur3.pdf — Metaheuristic MPC weight tuning (Nature SciRep 2025) | Journal article | 2 / 5 | PSO over self-play loss; sensitivity-analysis-first methodology |
| **R3** | heur2.pdf — KirbyBot CV thesis (Cal Poly 2018) | M.S. thesis | 2 / 5 | Decoupled perception/action; deadband thresholds; per-episode interaction logging |
| **R1** | heur0.pdf — Heuristic Pathfinding in Video Games (Lu) | Survey | 2 / 5 | Pre-computed scalar fields (sun-hazard map, influence map) |

**Highest-leverage sources are R6 and R8** — both score 4/5 and provide concrete, directly-portable patterns. Everything else is supplementary: useful for methodology and meta-patterns but not for specific formulas.

---

## Cross-cutting themes (patterns appearing in 3+ sources)

### Theme 1: A* `f = g + h` decomposition for target scoring
**Appears in: R1, R5** (and aligns with R6's mobility-score framing)

Replace the current "nearest-neighbor sniper" greedy logic with a true cost-plus-heuristic decomposition:

```
score(target) = g(commitment_cost) + h(estimated_remaining_cost)
```

For Orbit Wars:
- `g` = fleet-ships-needed-now + travel-time-cost (size-dependent fleet speed)
- `h` = expected-defense-growth-during-transit + sun-collision-probability + opportunity-cost of skipping this target

R5 explicitly diagnoses our current "nearest-planet sniper" as Greedy Best-First, which has a known failure mode: "susceptibility to local optima; it will eagerly pursue a node at the end of an exceptionally long or blocked path merely because the absolute heuristic coordinates appear close to the objective." That's exactly what our agent does.

**Admissibility discipline** (R1, R5): underestimate travel cost (so we don't spuriously reject viable captures); overestimate defensive cost (so we don't lunge into bad fights). Apply asymmetrically to different terms.

### Theme 2: Multi-tier value separation by orders of magnitude
**Appears in: R2, R8** (and confirmed by R6's tournament results)

Don't normalize features to [0,1] and add. Use multiplicative tiers so a higher-priority signal always dominates a lower-priority one:

```
score = 1e12 * term_terminal       # sure-win capture
      + 1e6  * term_decisive       # near-decisive (will outnumber + arrive first)
      + 1e3  * term_advantage      # tempo / threat / production gain
      + 1.0  * term_positional     # centre-of-mass, sun-distance, etc.
```

R2's H1 (Connect-4) used this exact structure: terminal=∞, near-forced-win=900,000, mild-advantage=50,000, opening-bonus=200/120/70/40. R8's "3-4 weak signals = 1 strong signal" calibration heuristic implies the same scaling: pick a strong feature with weight ≈ threshold, set weak feature weights ≈ threshold/4.

Use a large **finite** value (1e12) instead of `math.inf` to keep arithmetic safe (R2 open question).

### Theme 3: Phase-aware strategy switching
**Appears in: R6, R4** (and R5's state-aggregation pattern)

R6's headline finding: a single-line phase switch (`ratio = current_turn / max_turns; offensive() if ratio < 0.5 else defensive()`) outperformed every fixed-strategy heuristic in a tournament. Counter-intuitively, **offensive-early > defensive-early** — crippling opponent options before the board shrinks then conserving your own options late.

R4 used binary mode-switching of weights via a `sigma` gate per weight, rather than blending or hard-switching whole policies. Per-weight mode gating is a "middle ground worth trying" (R4).

For Orbit Wars (500-turn episodes):
- Phase ratio = `step / 500`
- Try multiple thresholds (0.3, 0.5, 0.7) and both orderings
- The winning strategy in our setting may differ from Isolation's; test empirically

### Theme 4: Asymmetric weighting (loss-aversion)
**Appears in: R5, R6** (and R8's FP/FN asymmetry)

Symmetric `mine - theirs` is suboptimal. Both R5 and R6 cite empirical wins from asymmetric multipliers:

- **R5 (GVGAI literature)**: weight `expected_loss * λ` with `λ > 1` against `expected_gain`. Loss-avoidance prioritized over point gain.
- **R6 (Isolation tournament)**: defensive `2*mine - theirs` and offensive `mine - 2*theirs` both beat the symmetric form.
- **R8 (cybersecurity)**: missing a real threat (FN) is much worse than over-defending (FP). Explicitly bias thresholds toward catching FNs.

For Orbit Wars where losing a planet is permanent damage (lost production for the rest of the game), λ should be > 1 on planet-loss terms. Sun and comet collision risks should drive λ even higher (no recovery from destroyed fleet).

### Theme 5: Predict-then-decide for moving targets
**Appears in: R7, R5** (and earlier project context — orbiting planets are a known pain point)

Every CV tracker in R7 uses the predict-then-decide pipeline: project tracklet positions to next frame, *then* associate detections. For Orbit Wars: project orbiting planet / comet / fleet positions to arrival turn, *then* aim the launch.

We already have `aim_with_prediction` in `world.py` (intercept solver) but `strategy.py` falls back to current-position aiming when intercept returns None — which may be the cause of our 30-40% win rate vs random. R7 explicitly warns: don't import a Kalman filter (we have ground truth + closed-form dynamics — Kalman would degenerate to identity). Just use the deterministic forward step.

### Theme 6: Pre-computed scalar fields
**Appears in: R1** (with R5 reinforcing as a pattern)

For a 100x100 board, a once-per-turn O(10^4) scalar field is trivially fast. Two useful fields:

- **Sun-hazard field** — for each (x,y) cell, compute hazard = inverse distance to the sun. Aim points outside high-hazard cells.
- **Influence field** — for each (x,y), compute `Σ player_fleet_strength × f(distance)` weighted by player. Targets in own-influence cells are safer; opportunities in contested cells are higher-EV.

Replaces per-fleet sun-distance checks and approximates the "broader landscape" intuition.

### Theme 7: Tournament-harness as a first-class regression test
**Appears in: R6, R2, R3** (R4 too via algorithm comparison)

Every research source that produced empirical results did so via tournament: opponent A vs opponent B over N trials. R6's `HeuristicManager` makes the heuristic pluggable; R2 ran ablation tournaments to rank features; R3 instrumented per-episode interaction logs.

We already have `uv run orbit-play ladder --opponents nearest_sniper,random` scaffolded. Extending it to A/B test heuristic *configurations* (not just opponents) is the next step. Two-heuristic round-robin per change request, ~50-100 episodes, win-rate matrix as the verdict.

### Theme 8: Hungarian assignment for fleet→target dispatch
**Appears in: R7** (uniquely high-impact)

Classical CV trackers use the Hungarian algorithm for one-to-one optimal matching. Direct port to Orbit Wars:

```
N owned planets with surplus garrison × M attractive targets
C[i,j] = travel_time(i,j) + λ × required_ships(j) - μ × strategic_value(j)
solve via scipy.optimize.linear_sum_assignment
```

This **replaces the "for each src, pick best target greedily"** loop with a globally-optimal one-to-one matching. O((N+M)³) is fine inside the 1-second budget for ≤ 50 planets.

Combine with **gating before assignment** (R7 §5): prune (i,j) pairs where (a) we can't win on arrival, (b) path is sun-blocked, (c) ETA exceeds horizon. Keeps the optimizer from ever proposing dominated launches.

### Theme 9: Tuning methodology — sensitivity analysis first, optimization second
**Appears in: R4** (with R2's ablation tournaments reinforcing)

R4's recipe (PSO over self-play loss): 
1. Coordinate-descent sweep one weight at a time first (cheap, surfaces obvious local optima).
2. Pairwise grid for weights flagged as suspicious (interdependency check).
3. Full PSO/GA only after the above narrows the search space.

L2 regularization on the weight vector (`R_w = ||W||²`, `η = 5` in R4) prevents the optimizer from latching onto huge weights that exploit simulator quirks.

For our setting (stochastic fitness — RNG-seeded comets, opponent variance), R4's recommendation of swarm-size = 2 is dangerous — we'll need ~10-30 with seed-averaging.

**Cheap calibration loop from R2** (online 1% adjust): after a loss, scale the agent's weights that contributed to losing by 0.99x. Iterate. Primitive policy-gradient without ML infrastructure.

### Theme 10: Selfish-routing / Tragedy-of-Commons in 4-player
**Appears in: R5** (uniquely)

In a 4-player game where everyone runs a similar greedy heuristic, mass-converging on the same high-value target is the failure mode. R5: "selfish-routing [collisions] result in global sub-optimization analogous to the Tragedy of the Commons."

Mitigation: penalize targets that we predict opponents are also racing toward. Even a crude `competitor_pressure(target) = Σ enemy_fleet_distance_to_target^-1` term shifts the balance.

This term is **specifically what's missing** from our current strategy and would matter most in 4-player FFA games.

---

## What didn't apply (saving us from dead ends)

| Pattern | Why we don't need it |
|---------|---------------------|
| Grid pathfinding (JPS, A* over cells, D*-Lite, LPA*, HPA*) | Continuous 2D with no static obstacles — just one moving sun. Fleets travel straight lines. |
| Kalman filtering / object tracking algorithms | Ground-truth observations + closed-form dynamics. Kalman would degenerate to identity. |
| Transformer / SSM trackers (SAMBA-MOTR, CAMELTrack, Cutie, DAM4SAM) | Off-budget for 1-second turn. Solve a problem (noisy detections) we don't have. |
| CNN / object-detection pipelines | We have structured `obs`, not pixels. R3's CNN content irrelevant. |
| Linear MPC weight optimization | R4's MPC math (state-space, constraints, SoC tracking) doesn't transfer to discrete-action RTS. Only the tuning meta-pattern is useful. |
| Cybersecurity-specific scoring (rule stacks for malware traits) | R8's domain-specific traits don't map. Only the architecture (additive scoring + tiered thresholds) transfers. |
| Connect-4-specific feature values (4-in-a-row patterns, 7×6 matrix) | R2's specific weights don't transfer. Only the tier structure does. |
| Re-identification / appearance embeddings | Entity IDs given by env. |
| Hierarchical clustering of planets | We have ≤ 50 planets — flat scoring is cheap enough. |

---

## Concrete actionable recommendations for our heuristic

Ranked by expected impact / effort ratio. Items 1-4 likely lift us from 30% vs random to >80% if executed cleanly.

### Tier A — Highest impact

1. **Restructure target scoring as `f = g + h` with multi-tier separation** (Themes 1, 2)
   - File: `src/orbit_wars/heuristic/targeting.py` (rewrite)
   - `g(target) = ships_to_send_now × cost_per_ship + travel_time_cost`
   - `h(target) = expected_defensive_growth + sun_collision_risk × penalty`
   - Score tiers: `1e6 * decisive + 1e3 * advantage + positional`
   - **Expected gain**: addresses R5's diagnosis that nearest-greedy is the wrong shape.

2. **Use intercept solver (`aim_with_prediction`) for ALL moving targets, not as fallback** (Theme 5)
   - File: `src/orbit_wars/heuristic/strategy.py` (rewrite the launch decision)
   - For static targets: `plan_safe_launch` is fine.
   - For orbiting / comet targets: ONLY use intercept; if intercept returns None, **skip the target rather than fall back to current-position aim** (which guarantees miss).
   - **Expected gain**: orbiting targets are ~78% of the board (everything within 50 of sun). Currently most launches at them miss.

3. **Add Hungarian one-to-one assignment for fleet→target dispatch** (Theme 8)
   - File: new `src/orbit_wars/heuristic/assignment.py`
   - Build cost matrix; gate dominated entries; solve via `scipy.optimize.linear_sum_assignment`.
   - Replace per-source greedy nearest-loop in `strategy.py`.
   - **Expected gain**: when N owned planets and M targets are similar, greedy always picks the same convergence — Hungarian distributes optimally.

4. **Add asymmetric loss-aversion weighting** (Theme 4)
   - File: `src/orbit_wars/heuristic/config.py`
   - Add `loss_aversion_lambda: float = 1.5` (tunable).
   - In `targeting.py`, multiply expected-loss terms (sun-collision, capture-fail, fleet-destruction) by `lambda`.
   - **Expected gain**: prevents reckless captures with negative EV.

### Tier B — Medium impact

5. **Phase-aware weight switching** (Theme 3)
   - File: `src/orbit_wars/heuristic/config.py`
   - Add 3 weight sets keyed by `step / 500` ranges (early/mid/late).
   - Test orderings empirically: offensive-first (R6's winner) vs defensive-first.

6. **Pre-computed sun-hazard field** (Theme 6)
   - File: new `src/orbit_wars/heuristic/fields.py`
   - Once per turn, build a 100×100 numpy array of `1 / max(distance_to_sun, 1)`.
   - Look up trajectory hazard by integrating along the path.

7. **Add competitor-pressure term for 4P** (Theme 10)
   - File: `targeting.py` (extend score)
   - Penalize targets that opponents are racing toward.

### Tier C — Methodology / infrastructure

8. **Build a tournament-harness with pluggable strategies** (Theme 7)
   - File: extend `tools/cli.py` (`ladder` subcommand)
   - Allow A/B testing different `HeuristicConfig` instances against fixed opponents.
   - Output: win-rate matrix + per-feature contribution log.

9. **Implement online 1% tuning loop** (Theme 9)
   - Self-play loop: run N episodes, identify weights that correlate with losses, scale by 0.99×, iterate.
   - Cheap calibration before reaching for PSO.

10. **PSO over self-play loss with L2 regularization** (Theme 9)
    - Once weights are roughly calibrated, fine-tune via PSO/CMA-ES.
    - Stochastic fitness → use swarm size 10-30, seed-averaging across episodes.

### Tier D — Nice-to-have

11. **Penetration-depth bonus** (R2): score bonus for fleet trajectories that threaten multiple targets along the path.
12. **Per-episode interaction logging** (R3): log `(my_ships, enemy_ships, owned_planets, comet_present, sun_distance_min)` per turn for post-hoc analysis.
13. **Random-move epsilon** (R2): every k turns, pick from top-2 to break deadlocks. Keep rare (e.g., 1/20 turns).

---

## Diagnosis of our current weakness vs. these findings

Going back to the heuristic-vs-random failure earlier: P0 ended games with 1 planet (just home) while random ended with 24-39. The research findings suggest two specific causes:

1. **Greedy Best-First failure mode** (R5). Our `score_target` was computing a weighted sum but still effectively picking nearest. R5 names this exact pattern as a known failure: agent eagerly pursues "blocked" paths because absolute heuristic coordinates look close. Fix: implement true `f = g + h` (Tier A.1).

2. **Orbital miss problem** (R7). Our launches at orbiting targets aim at current position; targets rotate during transit; fleets fly past; fleets exit the board destroyed. Fix: intercept-only for moving targets, no fallback to current-position aim (Tier A.2).

Either fix alone may solve the 30-40% vs random problem. Both together should put us solidly in the >80% range.

---

## Suggested next-session plan

Given the research, the right next move is **NOT** to keep tweaking the current strategy — it's to do one focused refactor session implementing Tier A items 1+2:

1. **Diagnostic first**: write a single small script that, given a seed, plays our agent vs random for 100 turns and *logs every launch* with: source, target_id, target_owner, target_is_static, target_radius, my_eta, my_ships_sent, target.ships_at_launch, did_capture (verified at fleet arrival turn). Run for 5 seeds, ~500 launches total. Find the actual failure mode empirically rather than from research priors.
2. **If diagnostic confirms "fleets miss orbiting targets"** (likely): implement Tier A.2 (intercept-only for moving targets). Re-run the 10-seed win-rate check.
3. **If diagnostic shows "fleets capture but agent under-attacks neutrals"** (also possible): implement Tier A.1 (`f = g + h` with multi-tier separation). Re-run.
4. **Iterate**: each fix gets a tournament check before the next is added (R6's methodology).

Tier A.3 (Hungarian) and A.4 (loss-aversion) come *after* we've validated the foundation, because they're worse than useless if the fundamental aiming is broken.

I have no opinion on the order of A.1 vs A.2 — the diagnostic in step 1 is what tells us which is the bigger lever.
