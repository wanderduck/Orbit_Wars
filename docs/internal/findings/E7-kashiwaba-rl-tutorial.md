# E7: kashiwaba-rl-tutorial

## Source
https://www.kaggle.com/code/kashiwaba/orbit-wars-reinforcement-learning-tutorial

## Fetch method
kaggle kernels pull (succeeded; .ipynb at /tmp/ow_e7/orbit-wars-reinforcement-learning-tutorial.ipynb, 78 KB, 41 cells). Extracted code+markdown via Python json parsing; orchestrator analyzed inline.

## Goal
Provide an officially-blessed PPO-based RL training scaffold for Orbit Wars that "outperforms the Nearest Planet Sniper agent from the Getting Started tutorial" (cell 0). Notebook explicitly markets itself as a starting point: "The current implementation makes several simplifying assumptions about the model, observations, and action spaces. To create a stronger agent, we recommend modifying the observation design, reward function, and aiming logic from this point forward" (cell 0). It is a tutorial, not a competitive submission — there is no leaderboard score reported.

## Methods

### Algorithm: PPO with self-play (cell 1)
- Per-planet decision unit: the policy is called once for each owned planet per turn. Each call produces a categorical distribution over target candidates.
- Multiple parallel envs collect rollouts; PPO updates run on the aggregated batch.
- Opponent is the same policy (self-play). Opponent weights are synced from the learner every `self_play_update_interval` updates (default 10–50).

### Action design (cell 2) — MASSIVELY simplified
- **`target_index = 0` = no-op; `target_index = 1..K-1` = candidate target picks. K = `candidate_count` (default 8).**
- **Ship count is NOT learned** — fixed rule `ships = max(target.ships + 1, 20)` lifted verbatim from bovard's sniper.
- **Aiming is NOT learned** — straight `atan2` from src to candidate target (likely sun-blind; notebook explicitly recommends fixing).
- For each owned source planet, candidates = `[no-op] + K-1 nearest other planets in distance order` (enemy/neutral/friendly mixed).

### Observation features (cell 3) — three groups, scalar features only
- **`self_features`** (per source planet): position, radius, ship count, production, is_rotating, # owned planets, # enemy planets, total owned ships, total enemy ships.
- **`candidate_features`** (per candidate): neutral/friendly/enemy flags, target position, relative position from src, distance, target ship count, target production, is_rotating, would-direct-shot-hit-sun, src ship count.
- **`global_features`**: turn progress, # friendly/enemy/neutral planets, total friendly/enemy ships, # friendly/enemy fleets in flight.

### Network architecture (cell 14, file `src/policy.py`)
```python
class PlanetPolicy(nn.Module):
    def __init__(self, self_dim, candidate_dim, global_dim, candidate_count, hidden_size=128):
        self.self_encoder      = MLP(self_dim     -> hidden_size -> hidden_size)
        self.global_encoder    = MLP(global_dim   -> hidden_size -> hidden_size)
        self.candidate_encoder = MLP(candidate_dim-> hidden_size -> hidden_size)
        self.target_head = MLP(hidden_size*3 -> hidden_size -> 1)  # per-candidate logit
        self.value_head  = MLP(hidden_size*3 -> hidden_size -> 1)  # state-value scalar

    def forward(self, self_feat, candidate_feat, global_feat, mask):
        # self_feat, global_feat: per-decision; candidate_feat: per-candidate
        # joint = concat(expanded_self, expanded_global, candidate) -> per-candidate logit
        # value head pools candidate embeddings via mean before scoring
        target_logits = target_head(joint).squeeze(-1).masked_fill(~mask, -inf)
        value = value_head(concat(self, global, mean(candidate)))
        return PolicyOutput(target_logits, value)
```
Three independent MLP encoders (each 2 linear+ReLU layers); concatenate `self || global || per-candidate`; per-candidate target logit head; value head with mean-pooled candidate embeddings.

### File structure (cell 7)
- `game_types.py` — observation→PlanetState/etc decoder
- `config.py` — `TrainConfig`/`EnvConfig`/`ModelConfig`/`PPOConfig` dataclasses + YAML loader
- `features.py` — feature builder + candidate selection
- `policy.py` — `PlanetPolicy`
- `ppo.py` — `sample_actions`, `ppo_update`, `safe_target_logits`, `TransitionBatch`
- `opponents.py` — `KaggleRandomOpponent`, `SelfPlayOpponent` (with `sync_from`)
- `env.py` — Kaggle environment wrapper
- `train.py` — orchestrates rollouts + PPO updates

## Numerical params / hyperparams

### Default training config (`PPOConfig` defaults from `src/config.py`, cell 11)
- `lr` = 3e-4
- `gamma` = 0.99
- `clip_coef` = 0.2
- `ent_coef` = 0.01
- `vf_coef` = 0.5
- `max_grad_norm` = 0.5
- `epochs` = 4
- `minibatch_size` = 512
- `rollout_steps` = 32
- `num_envs` = 4
- `total_updates` = 200

### YAML overrides for the public notebook run (`default_cfg.yaml`, cell 9)
- `total_updates` = 100 (with explicit comment: "**For full training, increase it to 2000.**")
- `num_envs` = 2
- `rollout_steps` = 64
- `minibatch_size` = 256

### Env config
- `candidate_count` = 8
- `ship_bucket_count` = 8 (defined but unused in this version since ship count is fixed)
- `max_planets` = 48 (state-tensor padding)
- `max_ships` = 400.0 (normalization)
- `max_production` = 5.0 (normalization)

### Self-play
- `opponent` = "self"
- `self_play_update_interval` = 50 (notebook config) / 10 (TrainConfig default)
- `self_play_deterministic` = false
- `alternate_player_sides` = true

### Model
- `hidden_size` = 128

## Reusable code patterns

### `safe_target_logits` (cell 15) — handles edge case where every candidate is masked
```python
def safe_target_logits(target_logits):
    invalid_rows = ~torch.isfinite(target_logits).any(dim=-1)
    if not invalid_rows.any(): return target_logits
    safe_logits = target_logits.clone()
    safe_logits[invalid_rows, 0] = 0.0  # force no-op when all candidates masked
    return safe_logits
```
Important pattern: when the per-decision row has no valid candidates (e.g., src planet has no ships to launch), force `target_index=0` (no-op).

### `ppo_update` (cell 15)
Standard PPO clipped-objective implementation:
- advantage normalization (`(adv - adv.mean()) / (adv.std() + 1e-8)`)
- ratio = exp(new_log_prob - old_log_prob)
- clipped policy loss = max(-adv * ratio, -adv * clamp(ratio, 1-clip, 1+clip))
- value_loss = 0.5 * (returns - value).pow(2).mean()
- entropy bonus -ent_coef * entropy.mean()
- gradient clipping at `max_grad_norm`
- inner loop: `for _ in range(epochs): for minibatch ...`

### Self-play opponent sync (cell 16)
```python
class SelfPlayOpponent:
    def __init__(self, cfg, device, deterministic=True):
        self.policy = PlanetPolicy(...).to(device).eval()

    def sync_from(self, source_policy):
        self.policy.load_state_dict(source_policy.state_dict())
        self.policy.eval()
```
Snapshot-based opponent — single frozen copy of the learner, refreshed every `self_play_update_interval` steps. **Not a league.** This is the simplest possible self-play and converges to RPS loops in many novel games (a known PPO-self-play failure mode).

### Returns calculation (cell ~20)
```python
future_return = group.reward + cfg.ppo.gamma * future_return * (1.0 - float(group.done))
```
Monte Carlo returns (no GAE in this tutorial). For 500-step episodes with sparse terminal reward this can be high-variance — explicit GAE would help.

## Reported leaderboard score
n/a — this is a tutorial. No leaderboard score is referenced anywhere in the notebook. Author explicitly markets it as a starting point that needs work to be competitive.

## Anything novel worth replicating

For our C2 RL scaffold (`src/orbit_wars/rl/`):

1. **Per-planet decision factoring** — the policy decides ONE planet at a time, not the full move list. Easier to learn, scales to any number of owned planets, naturally handles permutation. Adopt this factoring.
2. **Three-encoder feature decomposition** (self + global + per-candidate) with concatenation in target head — cheap to implement, no transformer needed for v1. We can upgrade to a set transformer later if needed.
3. **Top-K candidate gating** — instead of producing actions over ALL planets every turn, restrict to the K nearest. Massively reduces output dimensionality and matches how our heuristic thinks. Default K=8 is a reasonable starting point.
4. **Mask-then-softmax pattern** with `safe_target_logits` fallback to no-op — protects against degenerate states.
5. **Snapshot self-play with periodic sync** — simplest possible. Note: known to converge to rock-paper-scissors loops in many games; our spec §8.4 mandates a TrueSkill league instead. Use kashiwaba's sync mechanism as a building block but extend to a league per spec.
6. **Fixed ship count and dumb aiming as the v1 baseline** — separate the strategic decision (target selection) from the tactical/numeric decisions. We can layer learned ship-count and learned aiming on later (kashiwaba's `ship_bucket_count = 8` is already provisioned in the config but unused).
7. **YAML config + dataclass coercion** — clean separation of code and hyperparameters; useful for sweep tooling later.
8. **Default hyperparams as a jumping-off point** for our tuning sweeps (lr=3e-4, gamma=0.99 vs our spec gamma=0.997).

## Direct quotes / code snippets to preserve

### `PlanetPolicy.forward` (cell 14, verbatim)
```python
def forward(self, self_features, candidate_features, global_features, candidate_mask):
    self_hidden = self.self_encoder(self_features)
    global_hidden = self.global_encoder(global_features)
    candidate_hidden = self.candidate_encoder(candidate_features)
    expanded_self = self_hidden.unsqueeze(1).expand(-1, self.candidate_count, -1)
    expanded_global = global_hidden.unsqueeze(1).expand(-1, self.candidate_count, -1)
    joint = torch.cat([expanded_self, expanded_global, candidate_hidden], dim=-1)
    target_logits = self.target_head(joint).squeeze(-1)
    target_logits = target_logits.masked_fill(~candidate_mask, torch.finfo(target_logits.dtype).min)
    pooled_candidates = candidate_hidden.mean(dim=1)
    value = self.value_head(torch.cat([self_hidden, global_hidden, pooled_candidates], dim=-1)).squeeze(-1)
    return PolicyOutput(target_logits=target_logits, value=value)
```

### Default `PPOConfig` (cell 11)
```python
@dataclass(slots=True)
class PPOConfig:
    rollout_steps: int = 32
    num_envs: int = 4
    total_updates: int = 200
    epochs: int = 4
    minibatch_size: int = 512
    gamma: float = 0.99
    clip_coef: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    lr: float = 3e-4
    max_grad_norm: float = 0.5
```

## Open questions / things I couldn't determine

- **Reward function**: cell 0 mentions modifying it, but the notebook ships with what reward exactly? Most likely sparse terminal (win/loss) given Monte Carlo returns formula. Need to read `train.py` (cells 17+) to confirm.
- **Total wall-clock for the recommended `total_updates=2000`** — not stated. With 4 envs × 32 rollout_steps, that's 4 * 32 * 2000 = 256k env steps, much smaller than our spec's 10M target.
- **Ship count rule `max(target.ships + 1, 20)`** is borrowed from sniper — never accounts for in-flight production, sun avoidance, or fleet-speed scaling. Significantly handicaps the trained policy vs. our heuristic which already does these correctly.
- **Aiming logic** — straight `atan2` (per the implication of cell 0's "modifying aiming logic"). Sun-collision blind. Heuristic baseline (E6) already does this correctly.
- **No GAE** — pure Monte Carlo returns. High variance on 500-step episodes with sparse reward. Strongly recommend adding GAE in our C2.
- **No league / opponent diversity** — single snapshot opponent. Spec §8.4 mandates TrueSkill league; implement that instead.
- **`features.py`, `train.py` not read in detail.** Train loop structure, episode termination handling, and exact tensor shapes need verification when adapting code.
- **`alternate_player_sides=true` semantics** — does it physically swap player 0/1 in the env each rollout? Important for fairness during training.
- **No reported leaderboard score** — strongly suggests tutorial defaults are NOT competitive; the heuristic baselines (E6/E8/E9) are. We should not over-invest in matching kashiwaba's design — it's a starting point only.

### Implication for our v1 strategy

**This notebook is a tutorial, not a winning recipe.** Combined with the finding that E8 (LB-958) and E9 (LB-1224) are heuristic agents (NOT REINFORCE despite the slug names), the evidence on the public leaderboard so far is:

> **Heuristic agents are dominating the leaderboard. The only published RL implementation is a starter tutorial without a leaderboard score.**

This argues for re-weighting our roadmap: ship a strong heuristic v1 (per spec §7), and treat RL as opportunistic v3+ rather than the canonical iteration path. The user's earlier "RL-leaning" decision should be re-examined in light of E8/E9's heuristic nature — the synthesis brief will surface this for explicit user decision.
