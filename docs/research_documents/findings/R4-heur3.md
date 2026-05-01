# R4: heur3.pdf

## Source
/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/research_documents/heur3.pdf

## Document type
Peer-reviewed engineering / control-systems research article. Published in Nature Scientific Reports (2025) 15:41414, https://doi.org/10.1038/s41598-025-25319-3 (p. 1, p. 16). Open Access (CC-BY-NC-ND 4.0). Received 13 Aug 2025; Accepted 20 Oct 2025; Published 21 Nov 2025 (p. 16).

## Title and authors
"Comparison of metaheuristic algorithms set-point tracking-based weight optimization for model predictive control" by Kawsar Nassereddine and Marek Turzynski, Faculty of Electrical and Control Engineering, Gdansk University of Technology, Poland (p. 1).

## Pages read
All 17 pages (1-17).

## Goal
"To create and verify a weight optimisation technique for multivariable MPC based on set-point tracking" for a DC microgrid (battery + supercapacitor + grid + PV + load). The objective is "a repeatable, data-driven framework that improves control quality under various operating conditions and accelerates MPC weight selection" (p. 4). Concretely: tune the 20-weight cost function J of a linear MPC (Eq. 1, p. 4) using four offline metaheuristics — PSO, GA, Pareto search, Pattern search — and benchmark them on tracking error against demand (p. 1, abstract).

## Methods
- **System under control**: Hybrid energy storage DC microgrid managed by linear MPC implemented in MATLAB; state-space model with measured PV disturbance, hard + soft constraints (p. 4).
- **Cost function J (Eq. 1, p. 4)**: 20 weighted terms covering SoC tracking (battery and supercap), power tracking, control-effort penalties (alpha terms on power magnitudes), and rate-of-change penalties (lambda terms on Delta P). Each weight has a sigma-gated form `(S*sigma + (1-sigma)*S')` where sigma is a binary curtailment-period switch (low PV generation periods get different weights).
- **Loss function for tuner (Eqs. 2-6, p. 5)**: `L = E_w + eta * R_w` where `E_w = ||P_iw - R_Bi||^2` (squared norm of MPC's predicted SoC + grid power vs. reference trajectory + demand), `R_w = ||W||^2` is an L2 regulariser on the weight vector, and `eta = 5`. The MPC is rolled out with each candidate weight set, then loss is computed.
- **Four metaheuristics** (p. 6-8) compared: PSO (Eqs. 7-8), GA (Eq. 9), Pareto search (Eq. 10), Pattern search (Eq. 11). Same loss function across all four.
- **Sensitivity analysis** (p. 8-13): For PSO, sweep initial weights, max iterations, swarm span, swarm size, and (inertia, social, self-adjustment) including pairwise interdependencies via nested loops. For GA, sweep upper bounds, population size, selection/crossover/mutation operators, elite count, crossover fraction.
- **Evaluation metric**: `Error% = (P_dem - P_load) / P_dem` averaged over 24-hour load profile (p. 8). Each reported time is mean of 10 runs (p. 14).

## Numerical params / hyperparams
PSO final settings (Table 1, p. 7): swarm size = 2, max iterations = 200, bounds [0, 100], inertia range [0.5, 1.2], social adjustment = 2, self adjustment = 1.501. Best result: 1.9% error in 150 s (Table 6, p. 15).

GA final settings (Table 2, p. 7): population = 10, max generations = 50, bounds [0, 20], tournament selection, power mutation, scattered crossover, elite count = 1, crossover fraction = 0.6. Best result: 8.7% error in 366 s (Table 6, p. 15). With interdependent tuning, error went from 16% -> 13% -> ~8% (p. 12).

Pareto (Table 3, p. 8): max function evals = 1000, min poll fraction = 1, Pareto set size = 2, bounds [0, 100]. Result: 13.7% error in 372 s.

Pattern search (Table 4, p. 8): max iterations = 100, initial mesh size = 3, max function evals = 100. Result: 13.9% error in 64.2 s.

Loss regularisation: eta = 5 (p. 5).

PSO swarm-size sensitivity (Table 5, p. 11): sizes 2/5/10/20/30 -> errors 1.96/8.87/4.57/4.27/14.8 %, times 2.5/6.2/12.5/52.7/127.2 minutes. Non-monotonic; size = 2 was chosen for best speed/error trade.

## Reusable patterns for our heuristic
The paper itself is about MPC weight tuning, not RTS combat heuristics. The directly reusable content for `src/orbit_wars/heuristic/` is the **tuning meta-pattern**, not the controller mechanics:

1. **Multi-term weighted cost function as a heuristic skeleton**: The Orbit Wars heuristic likely scores candidate moves by a weighted sum of features (capture-value, distance, sun-collision risk, comet-evaporation risk, fleet-speed penalty, opponent-threat). Eq. 1's structure — many weights, each gated by a binary mode flag (`sigma`) — maps cleanly onto a heuristic that switches behaviour by game-phase (early/mid/late, ahead/behind, near/far from sun). Splitting weights by phase rather than blending one global weight is a defensible structural choice (p. 4).

2. **Offline weight tuning via PSO over self-play**: Their workflow — define an L2-regularised loss measured on rolled-out simulations, then have PSO search the weight vector — is portable. For us: define a loss = -(win rate vs. baseline opponents) + eta * ||W||^2; roll out N self-play episodes per candidate; let PSO search 5-20 heuristic weights. PSO's "1.9% error, 150 s, swarm of 2" result (Table 6) shows surprisingly small swarms can work when the search is well-bounded. **Caveat: it's "well-bounded" because the cost surface is smooth and deterministic; ours is stochastic (RNG-seeded comets, opponent variance), so swarm = 2 will collapse into a high-variance estimator — we'll need ~10-30 with averaging across seeds.**

3. **Sensitivity-analysis-first, optimisation-second ordering**: They run a single-parameter sweep before turning the full optimiser loose (Sec. "Sensitivity analysis", p. 8-13). For our heuristic with handful of weights, a coordinate-descent sweep (one weight at a time, others fixed) is cheaper than full PSO and provides good initialisation. Section "Effect of initial weight values on tracking performance" (p. 8) explicitly shows naive default init underperformed seeded init — directly translatable advice.

4. **Interdependency exploration via nested loops** (p. 9-10): Their key finding is GA dropped from 16% -> 8% only after they tuned (elite_count, crossover_fraction) jointly. For us this maps to: do not tune `weight_capture` and `weight_threat` independently — they trade off; sweep them on a 2-D grid. Likewise (`comet_avoidance`, `sun_avoidance`) likely have interdependence. Their warning that "PSO parameters do not exhibit hidden interdependencies that could otherwise lead to unexplored improvements" (p. 11) was confirmed by experiment, not assumed — a good template for documenting our tuning study.

5. **Recommendation: PSO over GA/Pareto/Pattern when latency matters**: PSO won on both error (1.9%) and wall-clock (150 s) because it parallelises naturally and uses simple velocity updates; GA's per-generation overhead and operator interactions make it slower (p. 14, Table 6). For Orbit Wars, where each "loss evaluation" is a 500-turn self-play episode (multi-second), PSO's smaller per-iteration overhead matters.

6. **Curtailment-period analogy**: Pareto and Pattern search "lacked precision during more dynamic phases" / curtailment periods (p. 12-13). The mechanistic explanation given (p. 13) — pattern search's local polls and step-size reduction force it to escape the old basin slowly when the optimum jumps — is a textbook warning for our setting: if the optimal heuristic weights differ between "ahead" and "behind" game states, a single-weight-set tuned on aggregated wins will underperform a phase-switched policy. Reinforces point 1.

## Direct quotes / code snippets to preserve
- "Loss function: L = E_w + eta * R_w" with `eta = 5`, `E_w = (norm(P_iw - R_Bi))^2`, `R_w = (norm(W))^2` (Eqs. 4-6, p. 5).
- "PSO algorithm achieved the lowest average error of 1.9% and an average computation time of 150 s, confirming its fast convergence, robust global search ability, and effective balance between exploration and exploitation." (p. 14)
- "incorporating parameter interdependency reduces genetic algorithm's power load tracking error from 16% to 8%, while particle swarm optimization achieves an error of under 2% even without considering interdependency." (p. 1, abstract)
- "Although no new minimum error below 1.96% was found, the analysis was essential to confirm that PSO parameters do not exhibit hidden interdependencies that could otherwise lead to unexplored improvements." (p. 11) — methodological lesson on negative results in sensitivity studies.
- PSO velocity/position update (Eqs. 7-8, p. 6): `v_i(t+1) = w * v_i(t) + C1*phi1*(pbest_i - x_i(t)) + C2*phi2*(gbest - x_i(t))`; `x_i(t+1) = x_i(t) + v_i(t+1)`.
- "It should be noted that the execution time is reported as the average of 10 runs, since it can fluctuate due to system-related factors independent of the random seed." (p. 14) — protocol cite for our timing reports.

## Anything novel worth replicating
- **Two-stage sensitivity analysis (independent then joint)**: For our heuristic tuning report, run each weight independently first (cheap), then run pairwise grids only for weight pairs flagged as suspicious — this is exactly what they did and it's defensible without being expensive.
- **Reporting both strengths and limitations per algorithm in a single table** (Table 6, p. 15): clean summary template for our own ablation tables.
- **Binary mode-switching of weights** (the `sigma` term in Eq. 1): under-used pattern in heuristic agents; usually we either blend or hard-switch entire policies. Per-weight mode gating is a middle ground worth trying for sun-proximity / endgame phases.
- **Surprisingly small swarm (size = 2) winning**: counterintuitive, worth a sanity-check experiment in our domain; if it holds we save tuning time. **Be sceptical**: their loss surface is deterministic and smooth; ours is stochastic — small swarms will likely fail.
- **L2 regularisation on heuristic weights** (`R_w = ||W||^2`): prevents the optimiser from latching onto huge weights that exploit simulator quirks rather than generalise. Cheap to add, worth it.

## Open questions / things I couldn't determine
- **Computational budget per evaluation**: Paper doesn't state the per-rollout simulation length / wall time of one MPC trajectory evaluation, only the total optimiser runtime. We can't compare directly to Orbit Wars 500-turn episodes.
- **Stochasticity handling**: Their MPC + load profile appears deterministic per run; how the metaheuristics would behave on a noisy fitness landscape (our case) is not addressed. Their suggestion that PSO swarm = 2 suffices is dangerous to copy without seed-averaging.
- **Why exactly 20 weights**: Eq. 1 has 20 weights but the rationale for that count vs. coupling/sharing is buried; only that they chose them to encode "fuel cost, SoC, demand tracking" priorities (Fig. 2). For our heuristic we'd want fewer for tractability.
- **Whether MATLAB defaults bias results**: They lean heavily on MATLAB Global Optimization Toolbox defaults (refs 40, 42, 44, 45, p. 17). Their winning PSO settings may not be portable to a Python (e.g. pyswarms, Optuna, scipy) implementation.
- **No statistical significance test** between 1.9% PSO and 8.7% GA — only mean of 10 runs. We can't tell if PSO truly dominates or if variance overlaps. We should report std/CI in our own version.
- **Curtailment-mode handling**: How they generated the binary `sigma` time series isn't fully specified; for us, the analogous mode-switch heuristic would need a clean event detector.

## Relevance to Orbit Wars (1-5)
**2 / 5.**

The paper's domain (linear MPC for DC microgrid) and methods (rolling-horizon optimisation under hard constraints, MATLAB toolbox) do not transfer to a discrete-action RTS heuristic. None of the cost-function structure (SoC tracking, power flow regulation) maps to fleet routing, capture mechanics, sun avoidance, or 4-player adversarial dynamics. The MPC-internal mathematics (state-space prediction, constraint handling) is irrelevant.

What survives the domain gap and pushes the score above 1: the **meta-pattern of using PSO/GA to tune a hand-designed weighted heuristic** (rather than RL), the **sensitivity-analysis-first methodology**, **L2 regularisation of weights**, **per-mode weight gating**, and the **explicit interdependency check**. These are general optimisation hygiene that our `src/orbit_wars/heuristic/` tuning loop should adopt — but they are present in dozens of generic tuning references; we don't need this paper specifically. If we already have a Bayesian-optimisation or PSO tuning paper in our research set, this one adds little. If we don't, the parameter tables (Tables 1-4) and the loss-function recipe (Eqs. 2-6) are a usable starting point.
