# Paper 6 — HA-DQN (Heuristic-Assisted DQN for Flexible Job-Shop Scheduling)

**Source PDF:** `paper6.pdf` in this directory.

## Executive summary

HA-DQN: a DQN that selects WHICH operation to schedule next, while a fixed heuristic (Earliest Completion Time First) selects WHICH machine and AGV will execute it — collapsing a 3-tuple action space to a 1-D one. The hybrid beats pure DQN/PPO and metaheuristics on flexible job-shop scheduling with AGV transport (12.63% makespan reduction at large scale), but the domain (single-agent static scheduling) is far enough from a 4-player real-time strategy game that the **architectural lessons transfer better than the algorithm itself**.

## 1. Title / authors / venue
"A heuristic-assisted deep reinforcement learning algorithm for flexible job shop scheduling with transport constraints." Xiaoting Dong, Guangxi Wan, Peng Zeng (Chinese Academy of Sciences). *Complex & Intelligent Systems* 11:210, published 17 March 2025 (p.1).

## 2. Problem setting
Flexible Job Shop with AGV transport (FJS-AGV): n jobs each with an ordered sequence of operations; m eligible machines per operation; v AGVs that physically move work-in-progress between machines. Objective: minimize makespan C_max (Eq. 1, p.4). Single-agent, fully observable, NP-hard, *static* (all jobs known up front, no opponents). This is a long way from Orbit Wars: turn-based competitive multi-agent vs. offline scheduling.

## 3. Method (HA-DQN)
Formulated as an MDP with 5 hand-crafted scalar state features (p.7-8): current makespan CM(t), total process time CPT(t), average completion percentage ACP(t), average machine utilization AMU(t), average AGV utilization AAU(t).

**Action set A is 9 dispatch rules** (Table 3, p.8): SJPT, LJPT, SOPT, LOPT, SJRPT, LJRPT, EOST, SMOPS, SOTT — the agent picks one rule per decision point, which selects the next OPERATION.

**Two heuristic sub-routines** (Algorithms 1 and 2, pp.9-10) then choose machine M_k and AGV V_s deterministically via Earliest Completion Time First (Eq. 23-24): M_k = argmin(release_time + transfer_time + process_time); V_s = argmin(release_time + no-load move time).

**Reward** r(t) = -(C_max(t) - C_max(t-1)) (Eq. 20, p.9), so cumulative reward equals -makespan when γ=1.

**Network:** standard DQN with online + target nets (synced every 5 steps), 3 ReLU hidden layers, RMSprop, experience replay, ε-greedy with adaptive linear-decay ε. Hyperparameters Taguchi-tuned: ε=0.90, γ=0.75, lr=0.005, λ=20, 2000 episodes, batch 64, replay 300 (p.11).

## 4. Key results (RPD = relative percentage deviation; negative = HA-DQN better)
- **Small benchmark** (Table 4, p.13): optimal in 6/10 instances, near-optimal in 4; up to 25.33% makespan reduction vs. ILS.
- **Medium** (Table 5, p.14): optimal MFJST01-05; large gap MFJST08 −23.39% vs. GA.
- **Large** (Table 6, p.15): always beats LAHC; mt10xyz, mt10xxxt, seti5cc reduce C_max by 12.63%, 11.29%, 10.97%.
- **Generalization** (Fig. 11, p.16): trained model transfers zero-shot to MK01-MK10 instances; 95s vs. LAHC's 10,768s on MK10.
- **Ablation** (Table 7, p.17): HA-DQN beats vanilla DQN by 7.74% (MK06) and PPO by 4.78% (MK02), with lower coefficient of variation (more stable).
- **Vs SOTA DRL baselines** (Table 8, p.17): outperforms PPO+GNN by up to 42.28% RPD and HGS by 38.79% on MKT07.

## 5. Heuristic-RL integration
Two distinct mechanisms stacked:
- **Action-space pruning via heuristic action set.** The DQN doesn't emit raw operations — it emits one of 9 named dispatch rules (SJPT, LJPT, …, SOTT). Each rule deterministically resolves to an operation given the current state. So heuristics serve as a *macro-action vocabulary* that compresses an unbounded action space into 9 discrete choices (p.8, p.9 "Heuristic-assisted machine and AGV selection algorithm").
- **Sub-decision delegation.** The 3-tuple decision (operation, machine, AGV) is decomposed: DQN picks the operation-via-rule; ECT heuristic picks machine and AGV. Authors explicitly state this *"can reduce the dimension of DRL action space heavily, thereby improving learning efficiency and convergence speed"* (p.9).

Not a policy prior, not reward shaping — pure architectural action-space factorization where RL handles the high-information-gain sub-decision and heuristics handle the well-modeled ones.

## 6. Strengths/limitations (per authors)
**Strengths:** scales to large benchmarks where metaheuristics time out (LAHC needed 2.5h for seti5xyz; HA-DQN <200s, p.13); generalizes zero-shot across instance distributions (p.16); more stable than vanilla DQN/PPO (lower Cov, Table 7). **Limitations** explicitly stated (p.19 Conclusion): "currently, our research considers only static scheduling … which limits the application of the proposed HA-DQN algorithm in dynamic scheduling environments." Future work flagged: dynamic/multi-objective/energy-aware variants, evolutionary integration.

## 7. Applicability to Orbit Wars
**Direct algorithm port: NO.** Domain mismatch is severe — single-agent vs 4-player adversarial; offline scheduling vs real-time per-turn 1-second budget; the 9 dispatch rules don't translate to a "send fleet" action vocabulary.

**Architectural lesson: HIGH value, 1-2 week feasible.** Concretely: Orbit Wars v1.5G already has a `use_hungarian_offense` toggle and many discrete heuristic strategies (greedy nearest-target, Hungarian assignment, defense-first, send-half vs. send-min-required). A bandit/Q-learning meta-controller that picks among ~5-9 named "playbooks" per turn, conditioned on hand-crafted state features (own ship total, opponent ship totals, owned-planet count, step/EPISODE_STEPS, threat count from `find_threats`), with reward = score-delta or end-of-game win indicator, is a near-clone of HA-DQN's pattern at a vastly smaller scale.

Key adaptation: Kaggle's stateless agent contract means training happens offline (self-play vs. opponents in `src/orbit_wars/opponents/`), and only the fitted Q-table/tiny-net ships in the tarball — fits the no-network-I/O constraint. Would address the open Hungarian-vs-greedy A/B by *learning* when to switch.

## 8. What couldn't be determined
Wall-clock training time on HA-DQN itself (paper reports inference time, not training time); exact network width/depth (says "three fully connected hidden layers" but no neuron counts, p.9); replay buffer warm-up policy; whether the 9 rules include any tie-breaking and how ties are broken; whether ε-greedy is per-decision or per-episode; how the 5 scalar state features are normalized for the network input (matters for stability with values like CM(t) growing unboundedly).
