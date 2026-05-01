# Paper 0 — HuRL (Heuristic-Guided RL)

**Source PDF:** `paper0.pdf` in this directory.

## Executive summary

HuRL (Heuristic-Guided Reinforcement Learning, NeurIPS 2021, Microsoft Research) accelerates RL by reshaping the MDP: it shortens the effective horizon via a smaller "guidance discount" while injecting a heuristic value function `h(s)` into the reward as a bootstrapping term, then anneals back toward the true horizon over training. For Orbit Wars this would require us first to have a working RL training loop (which we don't, in 7 weeks) and a value-function-style heuristic — making it conceptually elegant but structurally mismatched to our submission timeline.

## 1. Title, authors, venue/year
"Heuristic-Guided Reinforcement Learning" by Ching-An Cheng, Andrey Kolobov, and Adith Swaminathan (Microsoft Research, Redmond). NeurIPS 2021 (35th Conference on Neural Information Processing Systems), Sydney. arXiv:2106.02757v2, posted 22 Nov 2021. (p.1)

## 2. Problem setting / domain
Generic infinite-horizon discounted MDPs with unknown dynamics; RL acceleration when the practitioner already has prior knowledge expressible as a state value heuristic `h: S -> R` (e.g., from domain knowledge, expert demos, or offline RL). Validated on MuJoCo continuous-control (Hopper, HalfCheetah, Humanoid, Swimmer, sparse-Reacher) and Procgen procedural games (16 envs, RGB observations). (pp.1, 7-8, 23)

## 3. Method
Given an MDP M = (S, A, P, r, gamma) and a heuristic h, HuRL constructs a *reshaped* MDP M_tilde with:

- shorter discount `gamma_tilde = lambda * gamma`
- shaped reward `r_tilde(s,a) = r(s,a) + (1 - lambda) * gamma * E_{s'|s,a}[h(s')]`

with mixing coefficient lambda in [0,1]. lambda=1 recovers the original problem; lambda=0 collapses it to a contextual bandit using only h. The base RL algorithm (SAC, PPO, etc.) is run unchanged on M_tilde. Across iterations, lambda follows an INCREASING schedule: `lambda_n = lambda_0 + (1-lambda_0) * c_omega * tanh(omega * (n-1))`, so the agent first solves an easy short-horizon problem leaning heavily on h, then gradually anneals to the full horizon and discards the heuristic's bias (Algorithm 1, p.4; schedule p.21).

Theoretical core (Section 4): a bias-variance decomposition `V*(d_0) - V^pi(d_0) = Regret(h, lambda, pi) + Bias(h, lambda, pi)` (Theorem 4.1, p.5). Bias is invariant to constant offsets of h, depends on how well h orders states relative to V*, and is bounded by `(1 - lambda*gamma)^2 / (1 - gamma)^2 * epsilon` when h is epsilon-close to V*. Crucially, the authors introduce the novel concept of an *improvable* heuristic: h is improvable iff `max_a (Bh)(s,a) >= h(s)` (Bellman backup dominates h). For improvable heuristics, the bias drops dramatically — and they prove that *pessimistic* offline-RL value estimates (e.g., pessimistic value iteration) are guaranteed to be improvable, making them excellent HuRL heuristics (Propositions 4.4-4.5, p.7).

Distinct from PBRS (potential-based reward shaping by Ng-Harada-Russell '99), which preserves discount and merely re-shapes reward; HuRL changes both reward AND discount, providing strictly stronger horizon reduction.

## 4. Key results
MuJoCo (SAC base, 30 seeds): on Sparse-Reacher with an engineered heuristic `h(s) = r(s,a) - 100||e(s) - g(s)||`, HuRL converges while vanilla SAC and SAC+PBRS struggle. On dense-reward Hopper/HalfCheetah/Humanoid/Swimmer with Monte-Carlo regression heuristics learned from a batch of intermediate SAC checkpoints, HuRL-MC converges substantially faster than SAC, SAC+BC warm-start, and SAC+PBRS (Figure 2, p.9). Notably PBRS often *hurts* SAC because it changes value scales. Procgen (PPO base, 16 games): PPO-HuRL beats PPO on 8/16 games, ties on most others (Figure 4, p.25). Ablation on Hopper-v2 confirms that the gain comes from horizon shortening — increasing lambda above 0.98 degrades performance (Figure 2f, p.9).

## 5. Heuristic-RL integration
The heuristic is **explicitly a value-function prior**, integrated as both a reward bootstrap (`r + (1-lambda)*gamma*h(s')`) AND an implicit horizon-shortener (via reduced discount `lambda*gamma`). It is NOT a policy prior, NOT an action mask, NOT a search-tree pruner, NOT an exploration policy, NOT a curriculum opponent. The architectural pattern: heuristic provides a "good guess of long-term return" so the RL agent can learn from short rollouts and bootstrap the rest from h; as the agent improves it relies less on h. The heuristic is queried at every transition during training to compute the shaped reward — the heuristic must therefore be cheap to evaluate. Critically, h is consumed as a *scalar value function over states*, not as a black-box policy.

## 6. Strengths / limitations (per authors)
Strengths: theoretically principled (bias-variance decomposition, regret bounds), works with ANY base RL algorithm as a drop-in reward+discount transformation, complementary to BC warm-starting, robustness via increasing-lambda curriculum so a bad h doesn't permanently sink learning. Limitations (Section 7, p.10): "a bad heuristic can slow down learning"; lambda-scheduling requires per-environment hyperparameter tuning; effective construction of pessimistic offline-RL heuristics for high-dimensional problems remains open; the framework is evaluated only on single-agent envs.

## 7. Applicability to Orbit Wars
**Limited / structurally mismatched in the 7-week window.** HuRL presupposes you have (a) a working RL training loop on the env, (b) compute budget for many iterations (Procgen runs were 8M steps, ~1.75 hours each on a P40 GPU per seed per game), and (c) a heuristic expressible as a SCALAR STATE VALUE function V(s). Our v1.5G is a behavioral policy heuristic (greedy launch + defense planner producing ACTIONS), not a value function. To apply HuRL we would need: (i) a Gym-style wrapper for `kaggle_environments` orbit_wars (does not exist), (ii) a state-value head — possibly trainable by running v1.5G in self-play and Monte-Carlo regressing returns onto observations (analogous to the paper's Procgen heuristic construction, p.23), (iii) a base RL algo like PPO trained for millions of steps. Even a 1-2 week prototype is unrealistic given that the env wrapper, observation featurization, action-space discretization, and RL infra all need building from scratch. A more honest takeaway: if we ever DID build the RL stack (the v2+ direction noted in CLAUDE.md), HuRL's *framing* — bootstrap V from a heuristic-derived value, anneal lambda — is a strong template and the improvable-heuristic / pessimistic offline RL connection is theoretically motivating. For now: read, file, do not build.

## 8. What couldn't be determined from the text alone
- Exact wall-clock for MuJoCo experiments per seed (only "~1 hour for Hopper-v2") and total compute for the Procgen sweep across 16 games × 20 seeds.
- How sensitive HuRL is to *adversarial* multi-agent dynamics — all reported envs are single-agent. No multi-agent or self-play results reported.
- Whether `h` learned via Monte-Carlo regression from a behavioral policy (the most directly transferrable construction for us) was *improvable* in their experiments — they note (p.22) the basic VAE heuristic does NOT satisfy Proposition 4.5's assumption, leaving the empirical importance of strict improvability ambiguous.
- Whether the framework was ever evaluated with an *action-emitting* heuristic adapted into a value (e.g., rollouts of v1.5G's policy regressed into V) at competition-relevant scale.
