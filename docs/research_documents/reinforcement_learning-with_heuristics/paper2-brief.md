# Paper 2 — Tim Brys, "Reinforcement Learning with Heuristic Information" (PhD thesis, VUB 2016)

**Source PDF:** `paper2.pdf` in this directory.

**Note on this brief:** the paper is 132 pages (a doctoral dissertation). Two parallel agents covered pages 1-66 and 67-132 respectively; this brief consolidates their findings.

## Executive summary

A 2016 PhD thesis providing a unified taxonomy of how prior/external knowledge can be injected into temporal-difference RL, then validating the taxonomy across policy transfer, learning-from-demonstration, and ensemble-shaping settings. The central thesis: **knowledge encoding (V/Q/π) and injection mechanism are two orthogonal axes**, and most "novel" methods in the literature are recombinations of four primitive injection mechanisms (Q-init, dynamic shaping, PPR, extra action). The most directly transferable contribution for Orbit Wars is the proven-safe **Ensembles of Shapings** framework (Ch. 6), which lets a learner combine many heuristic signals without sacrificing convergence guarantees.

## 1. Bibliographic
"Reinforcement Learning with Heuristic Information," Tim Brys, PhD dissertation, Faculty of Science and Bio-Engineering Sciences, VUB, Brussels. Promotors: Ann Nowé (VUB) and Matthew E. Taylor (Washington State). Published 2016 by VUBPRESS as a book (ISBN 978-90-5718-448-2). 132 pages including bibliography. Document type: doctoral thesis / book — not a survey, but Chapter 3 functions as one.

## 2. Problem setting
RL is sample-inefficient because exploration is reward-driven and rewards are sparse in large state spaces. The thesis explicitly chooses the "inject heuristic knowledge" path over the "build inherently sample-efficient algorithms" path (p.5, p.25). Research question (Definition 1.1, p.16): *"How can one incorporate prior or external knowledge in a temporal difference RL process, aiming to increase the sample efficiency of this process?"* Base learner throughout: Q(λ)-learning with tile-coding function approximation. Tested on Cart Pole, Pursuit/Predator-Prey, and Super Mario.

## 3. The taxonomy (Chapter 3)
Brys decomposes any heuristic-RL method along three axes (p.31):

- **Type/source of knowledge:** transfer learning (prior task), demonstrations (state-action pairs), off-line advice (rules/heuristics), on-line advice/feedback (TAMER+RL, Knox & Stone 2010).
- **Encoding:** restricted to two — value function (V or Q) and policy (π) — because both are directly TD-usable. A pseudo-Q can be built from π by Q(s,a) = π(s,a) (p.35) — equivalent to a Ng-style potential function.
- **Injection** — four primitives:
  1. **Q-function initialization** (Q̂ ← Q_input): direct seeding, easy in tabular, awkward under FA.
  2. **Reward shaping** (R_F = R + F where F = γΦ(s')−Φ(s); Ng et al. 1999), extended to **dynamic shaping** where the potential Φ† is learned on-policy from a secondary reward R†, via Harutyunyan et al. 2015b — **this turns ANY reward function into a policy-invariant potential-based shaping signal**.
  3. **Probabilistic Policy Reuse** (PPR; Fernández & Veloso 2006): with probability ψ pick action from π_input, else ε-greedy; ψ decays.
  4. **Extra action**: append π_input as an extra "call the help line" action to the action set (Taylor & Stone 2007).

All four preserve convergence guarantees if applied properly (§3.3.5, p.39). Table 3.1 (p.40) classifies ~12 prior papers along {encoding} × {injection}, showing the literature is recombinations of these primitives.

## 4. Key empirical findings

**Chapter 4 — Policy Transfer (pp.45-63):**
- **No injection method dominates** across Cart Pole, Pursuit, Mario (§4.5). "No free lunch."
- Stochastic transferred policies (softmax τ≈0.1) outperform deterministic for init/PPR/shaping in Pursuit — broader bias is more robust when prior is partially wrong.
- In Mario, Q-init and Q-value reuse HURT vs baseline (Table 4.4) — Mario's state visitation is power-law; rare-state bias from a wrong prior dominates. PPR / dynamic shaping / extra-action win because their bias decays per-state-update or stays small.

**Chapter 5 — RLfD (pp.67-83):** novel **Gaussian value-function encoding** of demonstrations: Q^D(s,a) = max over demos of g(s,s^d,Σ) where g is non-normalized multivariate Gaussian. Essentially 1-NN in state space, producing a piecewise-Gaussian Q landscape "with mountain ranges along demonstrated trajectories." Gaussian wins for small datasets (init with 20 samples ≈ HAT/C4.5 with 2000); HAT scales better with large datasets. Even noisy hand-coded or low-quality demonstrators speed up learning (Fig. 5.7-5.8).

**Chapter 6 — Ensembles of Shapings (pp.85-110, the headline contribution):** Multi-objectivization decomposes one MDP into m correlated objectives by replicating the base reward and adding a different potential-based shaping F_i to each copy: **R(s,a,s') = [R+F_1, R+F_2, …, R+F_m]** (Eq. 6.1, p.93). Theorem 1 + Corollary prove this is a CMOMDP that **preserves the total ordering over policies** — so optimality and convergence guarantees survive. Each shaping spawns its own Q-learner; an ensemble policy combines them. Four ensemble strategies: **Linear**, **Majority Voting**, **Rank Voting**, **Confidence-based** (state-dependent weights from paired t-test on tile-coding weight distributions; scale-invariant, no parameters).

Empirical: with normalized shapings, all ensembles match or exceed a single composite shaping. **With non-normalized shapings, only the voting/confidence ensembles maintain performance — linear ensemble and naive composite collapse.** Pursuit shows ensembles outperform any single shaping. (Mario: naive composite slightly beats ensemble — author honestly flags this counter-example.)

## 5. Heuristic-RL integration
The taxonomy unifies all of {policy prior, reward shaper, action-set extension} under one menu of mechanisms. Any heuristic — demonstration trajectory, hand-coded policy, hand-designed potential function — gets converted to either a value function (Gaussian, C4.5, potential) or a policy, then injected via {Q-init, dynamic potential-based shaping, PPR, extra action}. **Ensembles of shapings is a reward-shaper-of-shapers**: each piece of heuristic knowledge becomes its own potential function and its own learner; combination happens at action selection.

## 6. Strengths / limitations
**Strengths:** unifying framework; experimentally demonstrates the four injection mechanisms; novel Gaussian RLfD encoding; the ensemble-of-shapings construction and CMOMDP soundness proof; empirically grounded "use confidence-voting when shapings have unknown scale" prescription. **Limitations** (Ch.7 Conclusions, p.111-115): all results in tile-coding linear FA — predates the deep RL boom; computational overhead of multiple Q-learners in the ensemble; recommends ordering when designing a system: PPR first (most consistently good), then init, then extra action, finally dynamic shaping (most complex/unstable); open problems: intra-signal scale-invariance, graceful degradation with bad shapings, automatic generation of shapings, validating with deep function approximators.

## 7. Applicability to Orbit Wars
**HIGH conceptual relevance, mechanically careful.** Two specific avenues stand out:

1. **PPR / Extra-Action with v1.5G as π_input:** Our agent IS the strong heuristic the framework assumes. We don't need to train RL from scratch (correctly identified as infeasible); we can use v1.5G as π_input and learn deltas. Stochastic-policy transfer beats deterministic — would suggest softening v1.5G to a softmax-over-launches when injecting it as π_input rather than greedy argmax. The Mario warning (Q-init catastrophic when most states are sparse) tells us to **prefer PPR/dynamic-shaping/extra-action over Q-init** for Orbit Wars (huge state space, rare states).

2. **Ensembles of Shapings for "which v1.5G knob"** (especially the unresolved Hungarian-vs-greedy A/B): cast each component (greedy nearest-target sniper, Hungarian assignment, defense reservation, late-game launch filter, map-control bonus, multi-source pincer) as a potential function over (planet ownership, fleet positions, ETA budget) feeding an ensemble. Each becomes its own Q-learner; **confidence-based voting** assigns state-dependent weights — this directly addresses "we don't know which knob to flip when" which is exactly our problem. Confidence ensemble's scale-invariance solves the scale-mismatch problem we'd otherwise have to engineer around.

**Caveats:** the dissertation only validates on Cart Pole/Pursuit/Mario with tile-coding Q-learning. Orbit Wars is 4-player RTS with combinatorial action space, 1s wall-clock, and would need deep function approximation that this thesis explicitly leaves to future work. Building the offline training infra (Gym-style wrapper, observation featurization, action-space discretization, Q-learner ensemble) is at minimum 1-2 weeks of scaffolding before any signal — at the edge of feasibility in our 7-week window.

## 8. What couldn't be determined
- Whether the Gaussian RLfD encoding extends beyond a single demonstrator or supports online demonstration.
- The Mario "PT" potential function used in ensemble experiments is referenced but Ch.4's full description was the prerequisite (covered in pages 1-66; second-half agent flagged this gap).
- Whether the four injection primitives behave qualitatively differently with deep-net function approximators (the thesis's own listed open problem).
- No multi-agent or adversarial validation — Pursuit is cooperative 2-predator, not FFA.
