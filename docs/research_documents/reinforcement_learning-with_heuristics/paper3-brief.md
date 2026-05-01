# Paper 3 — RL-Based Hyper-Heuristics (Review)

**Source PDF:** `paper3.pdf` in this directory.

## Executive summary

A 2024 review article surveying RL-based hyper-heuristics (RL-HH) — a meta-optimization paradigm where RL learns to select among a fixed pool of human-designed Low-Level Heuristics (LLHs) for combinatorial optimization (scheduling, TSP, VRP, packing). Directly relevant to Orbit Wars: our v1.5G already has multiple candidate sub-heuristics (greedy vs Hungarian offense, defense on/off) and the RL-HH framework offers a low-risk, low-data-budget pattern for learning *when to switch between them* rather than training a policy from scratch.

## 1. Title, authors, venue/year
"A review of reinforcement learning based hyper-heuristics," Cuixia Li, Xiang Wei, Jing Wang, Shuozhe Wang, Shuyan Zhang (Zhengzhou University). PeerJ Computer Science vol. 10, e2141, published 28 June 2024 (DOI 10.7717/peerj-cs.2141). Open-access review article, 31 pages.

## 2. Problem setting / domain
Selection hyper-heuristics for combinatorial optimization. Dominant test domains in cited corpus: scheduling (workshop, exam timetabling, flowshop, cloud task scheduling), VRP, TSP, packing/knapsack, and resource allocation (Table 2, p.19). Recurring meta-problem: given a pool of human-designed LLHs (swap, 2-opt, insertion, perturbation operators), pick the right one at each iteration to drive solution improvement.

## 3. Method
This is a survey, not a single algorithm. The authors formalize RL-HH as a two-layer architecture (Fig. 4, p.12): a control domain (High-Level Strategy = RL agent + Move Acceptance Strategy) and a problem domain (the LLH pool). Selecting an LLH is the RL action; LLH execution improves (or worsens) the solution; the delta becomes the reward; "state" is some encoding of recent LLH performance / problem features.

They split RL-HH into:
- **VRL-HH** (value-based): TRL-HH covering Q-learning, SARSA, multi-armed bandits, learning automata, transition-probability-matrix updates; and DRL-HH covering DQN/DDQN/D3QN.
- **PRL-HH** (policy-based): PPO, distributed PPO, A3C.

Eq. 3-4 (p.11) define Q(s, LLH_i) = E[R_t | s_t=s, LLH=LLH_i] with standard Bellman update; Eq. 5 (p.17) gives the policy-gradient update θ ← θ + α∇J(θ). Algorithm 1 (p.8) is vanilla tabular Q-learning with ε-greedy. The execution loop (p.3): (i) initialize LLH scores; (ii) apply selected LLH and let RL update its score from solution quality; (iii) at each decision point pick the next LLH from current scores; (iv) repeat until termination.

## 4. Key results
No first-party experiments — this is a literature review. Numerical comparisons are absent. The authors instead categorize ~80 RL-HH papers by RL method (Table 1, p.11) and application area (Table 2, p.19), and assert qualitatively that RL-HH "demonstrated exceptional value" (p.18). The strongest claims are that DQN-based DRL-HH (Dantas, Rego & Pozo 2021 on VRP/TSP; Tu et al. 2023 on online packing using D3QN with feature fusion) and PPO-based PRL-HH (Kallestad et al. 2023's DRLH; Qin et al. 2021's RLHH using DPPO + A3C for heterogeneous VRP) both improve robustness as the LLH pool grows (p.17).

## 5. Heuristic-RL integration
Exactly the "selector over heuristics" pattern. **Mapping to taxonomy: it's none of policy-prior, reward-shaper, or action-mask in the AlphaZero sense. It's a meta-controller / sub-heuristic switcher**: RL doesn't replace the heuristic; it picks WHICH human-designed heuristic to run next from a fixed LLH pool. Action space is small and discrete (cardinality = number of LLHs, typically 3-10). State is feature-engineered from solution quality history and recent LLH outcomes. Reward is per-step solution improvement (page 10). The Move Acceptance Strategy (MAS) is a separate module that decides whether to keep the candidate solution (p.6 Fig. 2). So **the heuristic stays authoritative — RL only does sequencing**.

## 6. Strengths / limitations (per authors)
**Strengths:** cross-domain generality (RL needs no problem-specific priors, p.2); small action spaces make tabular Q-learning viable for many real problems; PRL-HH scales to larger LLH pools without value-function explosion (p.17). **Limitations** (p.20): (1) no theoretical convergence analysis for RL-HH; (2) RL design quality dominates final performance; (3) poor adaptivity across problem instances; (4) computational cost vs real-time constraints; (5) no principled way to combine VRL-HH and PRL-HH. Authors also note PRL-HH suffers training instability and sample inefficiency (p.18).

## 7. Applicability to Orbit Wars
**Moderate-to-good fit, with caveats.** The pattern maps cleanly: v1.5G already has a `use_hungarian_offense` toggle and `reinforce_enabled` toggle, plus implicitly different launch-sizing / target-selection sub-policies. A 1-2 week prototype is feasible:

- **(a)** Define LLH pool = {greedy-offense, hungarian-offense, defense-only, idle, map-control-greedy}.
- **(b)** State = (game phase, fleet ratio, owned-planet count, threat presence).
- **(c)** Reward = Δ (own-ships − enemy-ships) per turn or terminal win/loss.
- **(d)** Tabular Q-learning over a discretized state, trained via self-play on the local sparring pool (which CLAUDE.md notes doesn't differentiate v1.4/v1.5/v1.5G — RL-HH might find a meta-policy that does).

Fits the 1-second `actTimeout` because inference is a Q-table lookup. **Risk:** the local opponent pool is saturated at 100% wins, so the reward signal may be too sparse to teach meaningful switching; needs the Kaggle ladder (3/day) as ground truth, which is too slow for online learning. Better as **offline-trained meta-controller** baked into the submission tarball, then ladder-validated.

## 8. What couldn't be determined
No quantitative win-rate or time-to-converge numbers — survey doesn't tabulate them. No state-encoding recipes (each cited paper engineers its own; review doesn't compare). No discussion of multi-agent / adversarial settings — every cited application is single-agent optimization, none are RTS or multi-player games, so transfer to a 4-player FFA is inferred not demonstrated. No code or pseudocode beyond vanilla Q-learning. No discussion of how state should encode opponent behavior, which is the actually hard part for Orbit Wars.
