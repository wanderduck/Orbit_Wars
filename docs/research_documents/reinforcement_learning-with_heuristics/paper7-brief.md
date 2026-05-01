# Paper 7 — LHBL (Limited-Horizon Search for Heuristic Value Learning)

**Source PDF:** `paper7.pdf` in this directory.

## Executive summary

"Beyond Single-Step Updates: Reinforcement Learning of Heuristics with Limited-Horizon Search" (Hadar, Agostinelli, Shperberg, arXiv 2511.10264, Nov 2025), which improves DeepCubeA-style approximate value iteration by replacing single-step Bellman updates with limited-horizon-search-derived labels on Rubik's Cube/STP/LightsOut. **Off-topic for Orbit Wars**: it learns shortest-path heuristics for single-agent deterministic puzzle domains with known goal states and full state observability — none of which apply to a 4-player adversarial RTS.

## 1. Title, authors, venue/year
"Beyond Single-Step Updates: Reinforcement Learning of Heuristics with Limited-Horizon Search," Gal Hadar (Ben-Gurion U.), Forest Agostinelli (U. South Carolina), Shahaf S. Shperberg (Ben-Gurion U.). arXiv:2511.10264v1 [cs.AI], 13 Nov 2025 (p.1). Venue not specified — appears to be a preprint with an "upon acceptance" code release note (p.5 footnote 1).

## 2. Problem setting / domain
Single-agent shortest-path problems where the objective is to reach a known goal state from a start state with minimum cumulative edge cost (p.1 abstract). Concretely evaluated on three combinatorial puzzles (App. A): 3×3×3 Rubik's Cube (4.3×10^19 states), 35-tile sliding puzzle (3.72×10^41 states), and 7×7 Lights Out (10^14 states). The aim is to learn a domain-specific heuristic h: V → R+ usable inside Batch-Weighted A* (BWAS).

## 3. Method
Builds on DeepCubeA's approximate-value-iteration (AVI) framing. Standard single-step Bellman-based learning (SSBL) trains a DNN heuristic h_θ via h_SSB(s) = min over neighbors s' of [c(s,s') + h_θ⁻(s')] (Eq. 3, p.3), with target network θ⁻ and MSE loss (Eq. 4).

Their proposed Limited-Horizon Bellman-based Learning (LHBL) replaces single-edge bootstraps with multi-step lookahead (Algorithm 1, p.4):
- Step 1 — Run a search (A*, GBFS) for N expansions from sampled start s, building search graph G(V,E).
- Step 2 — Add an auxiliary node z; for every leaf ℓ in G, add a directed edge ℓ→z with cost c(ℓ,z)=h_θ⁻(ℓ) (the target-net heuristic of the frontier node).
- Step 3 — Reverse all edges.
- Step 4 — Run Dijkstra from z on the reversed graph; the resulting distance from z to v is h_LHB(v) (Eq. 5: h_LHB(s)=min over leaves ℓ in L(n) of [C(n,ℓ) + h_θ⁻(ℓ)]).

The auxiliary-node + reversed-graph trick reduces "best path through any leaf descendant" to a single-source shortest-path problem that handles cycles in the partially expanded graph (p.4, Fig. 2). LHBL_S is an ablation that uses LHBL's biased state distribution (search-encountered states) but keeps the SSBL update.

## 4. Key results
All on three puzzle domains, BWAS evaluation with λ=0.6, batch sizes 1/100/1000/10000, three seeds, 10-min timeout per instance, RTX 4090/3090 training (3-12 days per run) (p.5). Headline numbers from Fig. 4 (p.7) at batch size 1 (where heuristic quality matters most):
- LightsOut 7×7: SSBL solves 4.7%, LHBL(50) **87.2%**, LHBL(100) 81.5%, LHBL_S(100) 74.2%.
- Rubik's Cube: SSBL 68.8%, LHBL(50) **95.0%**, LHBL(100) 92.3%, LHBL_S variants ~99%.
- 35-STP: all variants ~100% except SSBL 99.7% (LHBL still has order-of-magnitude lower node generations).

LHBL also reaches high solve rates in fewer training samples (faster sample efficiency) and produces 1-2 orders of magnitude fewer node expansions than SSBL at small batch sizes (Fig. 4 lower heatmaps). LHBL specifically shrinks "depression regions" — areas where learned heuristic underestimates true cost-to-go (Fig. 6).

## 5. Heuristic-RL integration
This paper's "heuristic" means an admissibility-relaxed cost-to-goal estimator h(s) used inside A*-family search — NOT a domain-rule policy like Orbit Wars' v1.5G. The "RL" is value iteration (DeepCubeA lineage). The integration interface: (a) the learned h_θ is the search guidance inside BWAS at deployment (p.3, Eq. 1); (b) during training the search itself produces both training-state distribution and label targets (Eq. 5). It is **not** a policy prior, action mask, or reward shaper — it is a value-function bootstrap target derived from limited-horizon search rollouts. The closest existing-RL analogue the authors cite is n-step SARSA (p.4); they extend that bootstrap idea to the entire descendant subtree.

## 6. Strengths / limitations (as authors describe)
**Strengths:** faster convergence vs SSBL, better sample efficiency, more reliable search (esp. small batch), mitigation of depression regions (p.8 conclusion). **Limitations** stated: "overly large horizons can introduce approximation errors or overfit to specific deep paths" (p.8) — sweet spot is N≈50 for STP/LightsOut. Implicit: requires DNN heuristic with target-net θ⁻ (no admissibility guarantee, p.2). No comparison vs LSS-LRTA* or policy-guided heuristic search baselines beyond SSBL/LHBL_S ablation.

## 7. Applicability to Orbit Wars
**Effectively zero direct applicability for the 7-week window.** Orbit Wars is (i) 4-player adversarial — there is no single goal state to compute shortest-path heuristics toward; (ii) stochastic / partially predictable opponents; (iii) action timeouts of 1 second per turn — no time for A*/Dijkstra on neural-net-evaluated graph; (iv) the domain has no natural "edge cost to goal" — outcome is win/loss after up to 500 turns. The whole framework presupposes a deterministic single-agent shortest-path MDP with known goal predicate.

**A 1-2 week prototype is infeasible:** it requires building a DeepCubeA-style training pipeline (the authors trained 3-12 days on RTX 4090), and even then the learned object (cost-to-go heuristic) is the wrong shape for Orbit Wars' v1.5G plug-in points (target scoring, ship sizing, defense reservation). The conceptual idea — "use multi-step lookahead inside a model to label training targets, not single-step Bellman" — is reusable if/when a v2 RL scaffold exists, but it solves a DeepCubeA limitation we don't yet face.

## 8. What couldn't be determined
Venue / acceptance status (preprint only). Exact LHBL training wall-clock per epoch (only end-to-end ranges given). Whether LHBL transfers to non-puzzle / stochastic / multi-agent domains — authors do not test or claim this. Whether the auxiliary-node trick handles negative or mixed-sign edge costs (Dijkstra requirement implies non-negative only, consistent with c: E → R+ in Sec. Background). Code is "to be released upon acceptance" (p.5 footnote 1) — not yet public.
