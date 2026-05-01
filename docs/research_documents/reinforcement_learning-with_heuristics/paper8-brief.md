# Paper 8 — RLA* (DQN-tuned A* Cost Weights for Off-Road Path Planning)

**Source PDF:** `paper8.pdf` in this directory.

## Executive summary

Xu et al. (2026, Robotics and Autonomous Systems) propose RLA*, a hybrid where a DQN learns to dynamically tune the cost-component weights of an A* path planner for off-road vehicles in unstructured terrain. The **RL-as-heuristic-tuner pattern** is conceptually transferable to Orbit Wars (DQN learning HeuristicConfig weights from observations), but the domain — single-agent geometric path planning — is sufficiently distant from a 4-player adversarial RTS that direct architectural reuse is limited; the high-level idea is what to borrow.

## 1. Title, authors, venue/year
"Reinforcement learning-driven heuristic path planning method for automated special vehicles in unstructured environment" by Fei-xiang Xu, Yan-chen Wang, De-qiang Cheng, Wei-guang An, Chen Zhou, Qi-qi Kou (corresponding). Robotics and Autonomous Systems 195 (2026) 105231, Elsevier. Received July 2024, accepted October 2025 (p.1).

## 2. Problem setting / domain
Global path planning for Automated Special Vehicles (ASVs) — emergency rescue, mining, agricultural vehicles — across unstructured rugged terrain with elevation, obstacles, slopes (p.1). Single-agent, deterministic, geometric. Map is a 2D grid with elevation per cell; start/end given; goal is a collision-free, smooth, vehicle-dynamics-feasible path (p.3-5). Not adversarial, not real-time, not multi-agent.

## 3. Method
RLA* (Reinforcement-Learning-based A*). Core A* cost: f(n) = ε₁·g(n) + (1−ε₁)·h(n) + ε₂·p(n), where g is path-cost-from-start, h is Euclidean-to-goal heuristic, p(n) is a height-difference penalty |z(n) − z(n−1)| (Eq. 8, p.4). The novelty: ε₁, ε₂ ∈ (0,1) are NOT fixed — they're produced per step by a DQN.

DQN setup (p.4, Eq. 9-12, Algorithm 1 p.5):
- **State** s(n): current node coords, deltas to goal, current cell height, plus an 8-vector of neighboring heights z(n) — 13-D input (Eq. 11).
- **Action** a(n) = (ε₁(n), ε₂(n)) — two continuous-valued weights (Eq. 12). (Discretization not specified despite DQN being for discrete spaces.)
- **Reward** r = −(k₁·r₁ + k₂·r₂) + k₃·r₃, where r₁ = height delta, r₂ = energy loss d_n·(F_g(n)+F_r(n)), r₃ = positive terminal-only reward (Eq. 13-15).
- Standard DQN loss with target net soft-updated every 10 steps (Eq. 10, 16). Discount γ=0.99, lr=0.0004, ε-greedy 1.0→0.01 over 100 episodes, 50K replay buffer, 128 batch, 4-layer FC net 16 hidden units PReLU, 1000 episodes (p.6).

Pipeline (Fig. 1, p.2): terrain analysis → passable-area mask → RLA* plans waypoints (RL emits weights, A* greedy-min(f) picks next cell) → cubic B-spline smoothing.

## 4. Key results
Two MATLAB simulated terrains, 30×30 and 20×20 grids, vs UT_A* (fixed-weight A*, two parameter sets), APF, GA. Metrics: Length, LSI (longitudinal stability index), HSS (horizontal smoothness score) (Table 2-4, p.7-9).
- **Scenario 1** average improvement vs UT_A* across 7 experiments: Length 16.1%, LSI 22.6%, HSS 3.0%; vs APF/GA roughly comparable in length but better in stability.
- **Scenario 2:** Length 24.6%, LSI 42.9%, HSS 1.4% improvement vs UT_A* (p.9).
- **Generalization** (Table 5, p.11): trained on region 1, tested region 2, 100% success rate vs APF 74%, GA 100% but with 727ms runtime vs RLA* 12ms.
- **Pure-RL ablation** (Table 7, p.12) shows highly unstable training — Length swings from 60 to 249 across episodes — supporting the claim that the heuristic prior is what stabilizes learning.

## 5. Heuristic-RL integration
**RL as heuristic-weight controller / cost-function tuner.** The agent does NOT pick actions in the environment — A* does that via greedy min(f). The agent picks the *coefficients of A*'s cost function* per step, conditioned on local observation (neighborhood heights). Explicitly stated p.4: *"the action a does not directly determine the ASV's movement direction... Instead, the agent of RL outputs two adaptive weights that modulate the cost evaluation of all eight neighboring directions."*

A* + heuristic (h to goal) eliminates the need for shaped exploration rewards (p.5: *"does not require incremental rewards to guide the vehicle step-by-step toward the goal... heuristic search can directly generate a complete path... resulting in a simpler reward design and more stable training convergence"*). Loose-coupling vs tight-coupling distinction is made explicit (p.2).

## 6. Strengths / limitations (per authors)
**Strengths:** stable training (Table 6 vs Table 7), generalization to unseen start-goal regions (Table 5), seed robustness (Table 8, reward 280-283 across 7 seeds), runtime far below GA. **Limitations** stated p.12: only simulated, will be deployed on real construction vehicle as future work; reward design will be enhanced with "step-wise differential rewards for terrain metrics such as LSI and HSS" — implies current rewards are blunt.

## 7. Applicability to Orbit Wars
**Conceptually relevant, mechanically distant.** Useful pattern: instead of training an end-to-end policy, train a small DQN to **predict HeuristicConfig values per turn** from observation features (planet ownership counts, fleet ETAs, threat counts) — letting the agent dynamically shift between offense/defense aggression, fleet-sizing factors, late-game launch ETA cutoff. This is plausible in 1-2 weeks because (a) network is tiny (4-layer FC, 16 hidden, ~hundreds of params), (b) RL search space is small (a handful of weights ∈ (0,1)), (c) v1.5G already provides the heuristic substrate analogous to UT_A*.

**Major obstacles:** Orbit Wars is 4-player adversarial — rewards aren't shaped by terrain physics but by win/loss against opponents whose policies shift; episodes are 500 steps not finite-horizon path completion; opponent diversity needed for training (the CLAUDE.md note that all local sparring is 100% beaten is precisely the bottleneck). The single-agent path-planning math (Eq. 5-8) doesn't transfer; only the **architectural pattern** transfers.

## 8. What couldn't be determined
How DQN handles the continuous (ε₁, ε₂) action space — paper says "DQN" but action is two reals; either implicit discretization or actor-critic is used but not described. Number of discrete (ε₁,ε₂) bins absent. Whether obstacles in the grid are also dynamic. No code/data link (p.12: "authors do not have permission to share data"). No comparison to MCTS or AlphaZero-style methods. Compute cost of training run unspecified.
