# RL-with-Heuristics — Cross-Paper Synthesis

**Date:** 2026-05-01
**Source PDFs:** `paper0.pdf` through `paper9.pdf` in this directory.
**Per-paper briefs:** `paper0-brief.md` through `paper9-brief.md` in this directory.
**Project context:** Orbit Wars Kaggle competition entry. Current baseline v1.5G (heuristic, ~800 μ on Kaggle ladder, mid-pack vs top of 1623). Deadline 2026-06-23 (~7 weeks remaining as of writing).

This document synthesizes findings across all 10 per-paper briefs, identifies recurring integration patterns, evaluates each pattern's feasibility for our submission, and answers the broader question of whether RL is a productive direction for our entry given our timeline.

## Executive summary

Five of the ten papers describe genuine RL+heuristic hybrids; two are pure single-discipline comparisons (no hybrid); the rest sit somewhere between. The hybrids cluster into **six distinct integration patterns**. For our 7-week window, only **two** are realistically prototypable: meta-controller / heuristic-selector (Pattern A — papers 1, 3, 6) and RL-as-cost-weight-tuner (Pattern D — paper 8). The others either presuppose RL infrastructure we don't yet have (training loop, env wrapper, deep-net function approximation) or solve a problem shape Orbit Wars doesn't have (single-agent search with a known goal).

**Bottom line on RL viability for our entry:** pure RL from scratch is firmly OUT (all 10 papers' compute and timeline assumptions exceed ours). RL as a small offline-trained meta-controller selecting between v1.5G's existing heuristic strategies is the only concrete RL avenue with realistic 7-week feasibility — and even that depends on solving the local-sparring-discriminator problem first (which CLAUDE.md flags as our biggest gap). A non-RL alternative — black-box hyperparameter search (CMA-ES / Bayesian optimization) over `HeuristicConfig` — plausibly yields comparable gains for less risk and less infrastructure cost.

## Per-paper at-a-glance

| # | Paper | Type | RL-heuristic pattern | Orbit Wars 1-2 week feasibility |
|---|---|---|---|---|
| 0 | HuRL (NeurIPS 2021) | Method paper | Pattern C: heuristic as value-function reward shaper (with discount horizon shortening) | NO — needs full RL stack and a V(s) heuristic we don't have |
| 1 | DRLH (EJOR 2023) | Method paper | Pattern A: PPO meta-controller picks ALNS operator | CONDITIONAL — needs v1.5G factored into a heuristic pool |
| 2 | Brys PhD thesis (VUB 2016) | Thesis / unifying taxonomy | Patterns B + C + F: catalogues all four injection mechanisms; introduces ensembles of shapings | CONCEPTUAL — taxonomy is invaluable; full implementation needs RL infra |
| 3 | RL-HH review (PeerJ CS 2024) | Survey | Pattern A: catalogues meta-controller variants | CONDITIONAL — same as #1 |
| 4 | DIDP RL guidance (arXiv 2024-25) | Method paper | Pattern E: RL-trained Q/π plugged into anytime DP search | NO — Orbit Wars isn't a DP-search problem |
| 5 | Atari Tetris H vs RL (ESWA 2025) | Comparative study | None (no hybrid) | NO transferable technique; reinforces heuristic > RL when sparse-reward |
| 6 | HA-DQN flexible job-shop (CIS 2025) | Method paper | Pattern A + action-space factorization: DQN picks dispatch rule, heuristic picks machine/AGV | YES — closest direct architectural template for v1.5G |
| 7 | LHBL puzzle search (arXiv Nov 2025) | Method paper | Pattern E: limited-horizon search labels for cost-to-goal heuristic learning | NO — puzzle search domain |
| 8 | RLA* off-road planning (RAS 2026) | Method paper | Pattern D: DQN tunes per-step A* cost weights | YES — closest template for "RL learns HeuristicConfig values" |
| 9 | Pathfinder student paper (n.d.) | Comparative study | None (no hybrid); methodologically weak | NO — useless |

Five rows useful (1, 2, 3, 6, 8); two patterns we can act on (A and D).

## Cross-paper integration patterns

The 10 papers describe (or explicitly contrast) variants of six recurring patterns for integrating RL with heuristics. Three of the patterns (A, B, D) keep the heuristic authoritative; one (C) uses the heuristic as a learning-acceleration signal; one (E) uses RL to learn the heuristic itself; one (F) combines many heuristics via learned weights.

### Pattern A — Meta-controller / heuristic selector
**Sources:** papers 1, 3, 6.
**Shape:** A discrete pool of N hand-designed sub-heuristics. The RL agent's action space *is* this pool (action_t = "use heuristic h_i for this turn"). State is a small feature vector summarizing problem progress. Reward is per-step solution improvement or terminal win/loss.
**Why it's interesting:** the heuristic remains authoritative — RL only does sequencing/dispatch. Action space is small and discrete (3-10 typical), making tabular Q-learning or tiny PPO viable. Train fully offline; deploy as a lookup table or tiny forward pass.
**Notable papers:**
- Paper 1 (DRLH): PPO + 12-D problem-independent state + 29-action ALNS pool. 13.5% improvement on CVRP-500 vs random selection; degrades only 0.02% when pool inflated to 142 heuristics (= learns to ignore bad ones).
- Paper 6 (HA-DQN): DQN picks one of 9 dispatch rules → heuristic decomposes which operation/machine/AGV. 12.6% makespan reduction vs LAHC, generalizes zero-shot to unseen instance distributions.
- Paper 3 (review): catalogues ~80 RL-HH variants across scheduling, VRP, TSP, packing.

### Pattern B — Heuristic as policy prior (PPR / extra-action)
**Source:** paper 2 Ch. 3-4.
**Shape:** Heuristic is invoked directly during exploration. Either with probability ψ (Probabilistic Policy Reuse, Fernández & Veloso 2006) or as an additional action in the agent's action set ("call the heuristic").
**Why it's interesting:** convergence-preserving (proven in §3.3.5); robust when the heuristic is partially wrong (because the bias decays per-state); the Mario experiment in paper 2 showed PPR beat Q-init catastrophically in power-law-state-visitation settings.
**Notable findings:** stochastic transferred policies (softmax τ≈0.1) beat deterministic across cart-pole/Pursuit/Mario — the broader bias is more robust to a partially-wrong prior. Implication for us: if we ever do PPR with v1.5G as π_input, we should *soften* v1.5G to a softmax-over-actions rather than greedy-argmax.

### Pattern C — Heuristic as reward shaper
**Sources:** paper 0 (HuRL), paper 2 Ch. 3-6.
**Shape:** Define a potential function Φ(s) from the heuristic; add F(s,a,s') = γΦ(s') − Φ(s) to the per-step reward (Ng-Harada-Russell 1999, policy-invariant). HuRL extends this to also reduce the discount γ → λγ, so the agent learns short-horizon problems first and anneals back to the true horizon. Paper 2's "dynamic shaping" (Harutyunyan 2015b) lets Φ be learned on-policy from any auxiliary reward, turning any heuristic-derived signal into a convergence-preserving shaper.
**Why it's interesting:** strong theoretical guarantees, drop-in to any base RL algorithm, accelerates learning when h is well-correlated with V*.
**Why it doesn't fit our 7-week window:** requires (a) a working RL training loop on the env, (b) compute budget for many iterations, (c) a heuristic expressible as a SCALAR STATE VALUE function V(s). Our v1.5G is an action-emitting policy, not a value function. Paper 0's reported MuJoCo experiments took ~1 hour per seed; Procgen took 1.75h on a P40 GPU per seed × 16 games × 20 seeds.

### Pattern D — RL as cost-weight tuner
**Source:** paper 8 (RLA*).
**Shape:** A heuristic algorithm has tunable parameters (e.g., weights in a multi-objective cost function). RL learns to predict good parameter values per state, conditioned on local features. The heuristic still produces actions; RL just picks the heuristic's hyperparameters.
**Why it's interesting:** small state, small action space, tiny network (paper 8 used 4-layer FC, 16 hidden units), search space is explicitly bounded (real-valued weights ∈ (0,1)). Trains fast, inference is cheap.
**Notable result:** paper 8's RLA* improved off-road path-planning length by 16-25% and longitudinal-stability by 23-43% vs fixed-weight A*; pure-RL ablation showed unstable training (Length swings 60-249 across episodes), confirming that the heuristic prior is what stabilizes learning.

### Pattern E — RL as h(s) for search
**Sources:** paper 4 (DIDP), paper 7 (LHBL).
**Shape:** Run RL offline to learn a value or policy network; use the network as the h(s) heuristic inside an A*-family or DP search algorithm at deployment.
**Why it doesn't fit:** Orbit Wars is not search-based. v1.5G is per-turn greedy/Hungarian assignment with no f = g + h hook. Even if we built one, the 1s actTimeout + 313×-slower-NN-per-node (paper 4 caveat, p.14) make this impractical.

### Pattern F — Ensembles of shapings
**Source:** paper 2 Ch. 6.
**Shape:** Decompose one MDP into M correlated objectives by replicating the base reward and adding a different potential-based shaping F_i to each copy: R(s,a,s') = [R+F_1, …, R+F_M]. Each shaping spawns its own Q-learner; an ensemble policy combines them via voting or confidence-weighted averaging. Theorem 1 + Corollary in paper 2 prove this is a CMOMDP that preserves the total ordering over policies — convergence guarantees survive.
**Why it's interesting:** scale-invariant (the confidence-voting variant requires no normalization between heuristics), provably safe, naturally handles "many partial heuristics" — exactly the situation we're in if we cast each component of v1.5G as its own shaping.
**Why it doesn't fit our 7-week window:** same reason as Pattern C — requires a working RL training loop and per-shaping Q-learners.

## Things explicitly NOT worth pursuing

- **Pure RL from scratch on Orbit Wars in our remaining time.** All 10 papers' implicit compute requirements (paper 0: ~1.75h × 16 games × 20 seeds; paper 4: 72 hours; paper 5: 17-39h training that *failed* to learn line-clearing in Tetris; paper 7: 3-12 days RTX 4090) exceed our window. Paper 5 specifically demonstrates that pure RL on a sparse-reward, large-state-space game can fail catastrophically against a hand-coded heuristic — exactly our setting.
- **Search-based heuristic learning (Pattern E).** Wrong domain shape; DIDP-style anytime search is incompatible with our 1s actTimeout.
- **Implementing paper 9's tabular-Q-vs-Dijkstra setup as any kind of template.** It's a methodologically weak student paper offering no integration pattern.
- **DeepCubeA-style approximate value iteration (paper 7).** Wrong problem class (single-agent puzzle with known goal state).
- **Neural network function approximators trained in the next 7 weeks for an end-to-end policy.** Multiple papers (5, 6, 8) show pure deep RL is unstable on sparse-reward problems and is best used as a *small* meta-controller layered over a heuristic, not as a from-scratch policy.

## Orbit Wars feasibility per pattern (the answer to "could RL lead us in a positive direction")

| Pattern | Direct fit? | Prototype effort (1-2 weeks?) | Likely impact on ladder | Risk |
|---|---|---|---|---|
| A — Meta-controller | YES, with refactoring | YES (tight) | Uncertain — small but possible μ gain if local sparring discriminates | MEDIUM. Local opponent pool doesn't differentiate strategies (CLAUDE.md), so training signal may be weak. Paper 6 needs the "right pool of heuristics" to exist; we'd be starting with 3-4 toggles. |
| B — Policy prior (PPR / extra-action) | CONCEPTUAL | NO (needs RL stack) | N/A in this window | High — needs RL infra we don't have |
| C — Reward shaper | CONCEPTUAL | NO | N/A in this window | High — needs RL infra and a value-fn-shaped heuristic |
| D — Cost-weight tuner | YES, with adaptation | YES (tight) | Uncertain — could replace static `HeuristicConfig` with state-dependent values | MEDIUM-HIGH. Adversarial reward signal makes training hard; same local-sparring problem as A |
| E — Search h(s) | NO | N/A | N/A | N/A |
| F — Ensembles of shapings | CONCEPTUAL | NO | N/A in this window | High — same as C plus per-shaping training overhead |

### Concretely, the two patterns we *could* prototype

**Option A — meta-controller in ~1-2 weeks:**
1. Factor v1.5G into a discrete pool of 4-8 named strategies. Concrete starting point: `{greedy-nearest, hungarian-assignment, defense-only, swarm-on-weakest-enemy, comet-snipe, hold-and-build}`. Some already exist as toggles; others would need to be split out.
2. Define state vector ~5-12 hand-crafted features: (own_ship_total / total_ship_count, owned_planet_count, threat_count from `find_threats`, step / EPISODE_STEPS, turns_since_last_capture, fleet_aggression_ratio, last_action one-hot).
3. Reward: terminal win/loss, plus optional dense shaping (Δ own-ships per turn).
4. Train tabular Q-learning or tiny MLP-PPO **offline** via self-play against the local sparring pool. Bake the trained Q-table / network into the submission tarball.
5. Ship; ladder-test using the spec's standard cadence.

Estimated cost: 3-5 days for refactoring and infrastructure, 3-5 days for training/tuning, 1-2 days for ladder-testing. Tight against our 7-week budget; requires no new dependencies.

**Option D — cost-weight tuner in ~1-2 weeks:**
1. Identify ~5 `HeuristicConfig` weights with the most plausible state-dependence (e.g., `safety_margin`, `late_immediate_ship_value`, `ahead_attack_margin_bonus`, `defense_buffer`, late-game ETA cutoff).
2. Define same state vector as Option A.
3. Tiny DQN (or even a regression model) maps state → weight values. Train via offline self-play with reward = win/loss.
4. At inference, every turn: state → weights → pass to v1.5G as a `HeuristicConfig` instance (already supported via the `config` argument to `agent`).

Estimated cost: similar to A. Less invasive (doesn't restructure decision flow) but possibly weaker signal since the changes are continuous-knob rather than discrete-strategy.

### A non-RL alternative worth comparing against: black-box hyperparameter search

Multiple papers (paper 5 §6.3, paper 8 implicit) point at the same insight: most of the gains attributed to "RL tuning" can also come from blind black-box optimization (CMA-ES, Bayesian optimization, evolutionary search) over the heuristic's hyperparameters. **Trade-off:** black-box search is much simpler to implement (no MDP framing, no replay buffer, no neural network), trains the same way (offline self-play loops), and can exploit the same compute. Its main weakness is no state-dependence — it produces a single best static configuration, not a state-conditioned policy. For Orbit Wars specifically, since v1.5G is already a strong static heuristic, an offline CMA-ES sweep over `HeuristicConfig` might recover most of the gain Option D promises with significantly less infrastructure risk. **This is not RL** but it IS the natural baseline against which we should evaluate any RL-based meta-controller.

## Recommended directions

Ranked by (likelihood of producing measurable ladder gain) × (likelihood of completing in our window) × (low infrastructure risk):

1. **Black-box hyperparameter search over `HeuristicConfig` via CMA-ES or Bayesian optimization.** Not technically RL. Simplest to build (no MDP), reuses our self-play loop. Sets a baseline for any RL approach to beat. Estimated 1 week.
2. **Option A — meta-controller picking among 4-8 named v1.5G strategies.** Closest to all three "useful" RL+heuristic patterns (papers 1, 3, 6). Tabular or tiny MLP. Trained offline. Estimated 1.5-2 weeks.
3. **Option D — DQN tuning HeuristicConfig values.** Cheaper than full RL, less invasive than Option A. Worth attempting *after* Option A returns signal (or doesn't). Estimated 1.5-2 weeks.
4. **Conceptual: Pattern B (PPR / extra-action) for a v2 RL stack** — defer to post-deadline if we want to invest in a proper RL infra for future competitions. Brys' thesis (paper 2) is the right starting reference.

Items NOT recommended for our window: Patterns C, E, F; pure RL anything; replacing v1.5G; building a deep network end-to-end policy.

## Honest take on the broader RL question

The user's question was: "could RL lead us in a positive direction within the leaderboards?"

**The honest answer is: marginally, and with significant infrastructure cost and uncertain signal.** Here's the actual state:

1. **The competition deadline is binding.** ~7 weeks remain. None of the 10 papers report end-to-end training-and-deploy cycles short enough to fit comfortably inside that window. Even the small-network RL hybrids (paper 8's 4-layer FC, paper 1's MLP) describe weeks of iteration to get a working pipeline.

2. **Our local opponent pool is the binding constraint, not the RL framework.** CLAUDE.md flags that all current local sparring partners give 100% win rate against v1.4/v1.5/v1.5G. Per the Phase 2 work (mdmahfuzsumon ported as a peer-strength sparring partner), we now have ONE discriminating opponent — but RL training generally requires *opponent diversity*, not just one stronger partner. Without that, our RL training signal will be biased toward exploiting that one opponent rather than learning generalizable policy.

3. **The most plausible RL path is also the most modest.** If we did Option A (meta-controller) and it worked, we'd likely see a +20 to +50 μ ladder shift if the trained meta-policy generalizes — comparable to what one or two well-chosen heuristic refinements could achieve directly. The expected value is positive but not transformative; it almost certainly does not get us into the top 10.

4. **The field consensus from these papers is "RL augments good heuristics; it does not replace them in 7-week windows."** Paper 5 explicitly demonstrates pure RL failing where heuristics succeed; paper 8 demonstrates pure-RL ablation being unstable; paper 6 shows that constraining RL's action space with heuristics is what makes it work; paper 0's HuRL is explicitly motivated by "RL is too sample-inefficient on its own — it needs heuristic-derived value signals."

5. **For a Kaggle submission specifically, the main risk of RL is opportunity cost.** Every day spent building RL infrastructure is a day not spent on heuristic refinement (where we have known leverage points: multi-source coordination, vulnerability-window scoring, sun-tangent bypass routing — all flagged in the Phase 1 synthesis). The Phase 2 spec already has 4 heuristic refinements queued (Step 1 done, Step 2 ladder-tested negative, Steps 3a and 4 pending). Diverting to an RL prototype now means deferring Steps 3a and 4 — possibly indefinitely.

**My recommendation:**
- **Do not pivot Phase 2.** Continue with the current plan (Step 3a path-collision instrumentation; Step 4 multi-source pincer) — these have known scope, known signal pathway via the existing local A/B gate, and direct ladder testability.
- **In parallel, if you have spare cycles**, run the black-box CMA-ES sweep over `HeuristicConfig`. It's cheap, requires no new framework, and gives us the natural baseline against which to evaluate any future RL effort. Two days of work; could yield a quiet +10-30 μ.
- **Defer the meta-controller (Option A) and cost-weight tuner (Option D) to a Phase 3 decision** — if Phase 2 wraps with time remaining and the heuristic refinements have plateaued, then a meta-controller becomes a defensible 2-week investment. If Phase 2 burns the budget, we ship v1.5G + whatever Phase 2 refinements survived.
- **Keep these 10 briefs and this synthesis as a reference for any post-competition RL build.** Paper 2 (Brys' thesis) and paper 6 (HA-DQN) are the highest-quality conceptual templates if we ever build out the RL stack properly.

In short: RL is not the path to top-10 in our remaining window. Heuristic refinement is. But RL is the path to the *next* competition in this style, and these papers are the right map for it.
