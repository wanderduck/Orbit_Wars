# Paper 4 — RL-as-Heuristic for Domain-Independent Dynamic Programming

**Source PDF:** `paper4.pdf` in this directory.

## Executive summary

Trains DQN/PPO agents on combinatorial optimization MDPs (TSP, TSPTW, Knapsack, Portfolio) and uses the learned value/policy as a heuristic h(s) inside Domain-Independent Dynamic Programming (DIDP) state-space search, beating hand-crafted greedy heuristics in 3 of 4 domains. The paradigm is **RL-as-heuristic-for-DP-search** — strongly relevant to RL+heuristic hybridization in principle but architecturally targeted at offline-trained search guidance for single-agent combinatorial DPs, not real-time multi-agent RTS.

## 1. Title, authors, venue/year
"Reinforcement Learning-based Heuristics to Guide Domain-Independent Dynamic Programming" by Minori Narita, Ryo Kuroiwa, J. Christopher Beck (University of Toronto + NII Tokyo). arXiv:2503.16371 (2024-2025); style/format suggests CPAIOR or ICAPS submission. (p.1, p.3 footnote 3)

## 2. Problem setting / domain
Domain-Independent Dynamic Programming (DIDP) is a state-space search paradigm where users define a DP model in DyPDL (Bellman-equation based) and solvers do best-first/anytime search. Default h(s) is a user-defined dual bound — admissible but often not informative (p.1). Authors replace this dual-bound h(s) with one learned by RL on an MDP that is mechanically derived from the same DyPDL model. Tested on TSP, TSPTW, 0-1 Knapsack, Portfolio Optimization (single-agent combinatorial optimization, deterministic transitions, finite horizon). (pp.7-12)

## 3. Method
A DyPDL tuple ⟨V, s₀, T, B, C⟩ is mapped 1-to-1 to MDP ⟨S, A, T, R⟩ (Fig. 1, p.5): DIDP states → MDP states; transitions τ → actions a; preconditions pre_τ → action mask; transition cost cost_τ(s) → reward R(s,a) = β · cost_τ(s) (negated for minimization, scaled by β ∈ {0.001, 0.0001} for stability). State constraints C are NOT mapped (left to future work, footnote 4 p.5).

Two variants:
- **Value-based guidance (DQN):** train DQN on the mapped MDP, set h(s) = −V^θ(s) where V^θ(s) = max_{a∈A'} Q^θ(s,a) over applicable actions; f(s) = g(s) + V^θ(s) (Sec. 3.1, p.6).
- **Policy-based guidance (PPO):** train PPO, weight f-value by accumulated path probability π†(s⁻,a⁻) = π(s₀,a₀)·…·π(s⁻,a⁻); f(s) = (g(s) + η(s)) · π†(s⁻,a⁻) for max problems, divide instead of multiply for min (Sec. 3.2, pp.6-7). Promising actions get higher f-value → expanded sooner.

State encoders: Graph Attention Networks for routing (TSP/TSPTW), Set Transformer / Deep Sets for packing problems (Knapsack/Portfolio) — chosen for size-agnostic permutation invariance (p.7). Search algorithms: CABS, ACPS, APPS (anytime variants, p.3).

## 4. Key results (Table 1 p.15; Fig. 3 p.13)
- **TSP n=50 (CABS):** π=PPO gap 3.89% vs dual-bound 8.30% vs greedy 2.79%; PPO best of all DIDP methods.
- **TSPTW:** RL trained directly on TSPTW MDP performs WORSE than h=0 (constraint masking interferes); using TSP-trained RL inside TSPTW DIDP recovers parity with greedy. All methods reach ~20/20 feasible at n=20.
- **0-1 Knapsack:** all heuristics within 1%; DQN/PPO converge to greedy best-ratio policy.
- **Portfolio n=50 (CABS):** π=PPO 0.19% gap vs dual-bound 8.30% vs BaB-DQN baseline 10.8%; PPO substantially outperforms.
- **Caveat (p.14):** RL inference is **~313× slower per node** than dual-bound, so wall-clock advantage is narrower than node-expansion advantage.

## 5. Heuristic-RL integration
RL acts as a **learned heuristic h(s) that replaces the static dual bound inside an exact/anytime search**. Two interfaces: (a) value-based — Q-network plugged in as h(s) in f = g + h; (b) policy-based — actor-network output multiplies the f-value as a search-priority weight (a soft branch ordering). Action masking from preconditions is the only "rules" injection. Training is fully offline (72-hour budget, p.8) on synthetic instances from a fixed distribution; the heuristic is then frozen for search.

## 6. Strengths / limitations (per authors)
**Strengths:** natural DP↔MDP mapping enables systematic h(s) learning; PPO guidance beats hand-crafted greedy in TSP and Portfolio (p.14, "PPO heuristic is better at driving the search towards high quality solution"). **Limitations** explicitly noted: (a) NN call dominates per-node time (p.15 "computational overhead"); (b) state constraints not mapped — TSPTW result shows constraint-heavy domains hurt direct RL training (p.13 "even worse than h=0"); (c) one network per problem-size (no scalability study, p.8); (d) the systematic mapping is currently manual.

## 7. Applicability to Orbit Wars
**Low direct fit, but the paradigm is suggestive.** Mismatches:
- (i) Orbit Wars is multi-agent FFA real-time strategy with 1-second turn budget — DIDP's anytime tree search at 1280 samples and 313×-slower-NN-per-node is incompatible with `actTimeout=1`.
- (ii) v1.5G is not a search algorithm with an h(s) hook — it's a per-turn greedy/Hungarian assignment, so there is no f = g + h to plug into.
- (iii) DIDP requires a clean DyPDL model, which Orbit Wars (rotating planets, comets, fleet-speed-from-size, path-collision physics) doesn't naturally admit.
- (iv) Results assume offline training on synthetic distribution — Kaggle ladder distribution is opponent-mix-dependent and shifting.

**1-2 week prototype: NOT FEASIBLE as described.** Possible analog: train a small NN to score (source, target) launch pairs offline from self-play replay logs, replace the current `nearest-target` cost with NN-scored cost in the existing Hungarian/greedy assignment (PPO-style policy as priority weight). That bypasses the search-tree assumption but is several weeks of scaffolding before signal.

## 8. What couldn't be determined
Total training compute (only "72 hours" and "8 GB memory" stated, no GPU spec, p.8). Network architecture details (deferred to arXiv Appendix B, not in this PDF). Whether PPO's win on Portfolio generalizes to out-of-distribution instance sizes. How action-masking would have behaved if state constraints C were mapped (authors explicitly defer per Huang & Ontañón 2020, footnote 4 p.5). No multi-agent or partially-observable variants tested.
