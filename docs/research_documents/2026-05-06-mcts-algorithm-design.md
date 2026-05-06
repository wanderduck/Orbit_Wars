# MCTS algorithm design — 2026-05-06

**Status:** v2 — REVISED 2026-05-06 after reading the user-supplied references
in `docs/research_documents/mcts/` (Aljabasini 2021 master's thesis on
Simultaneous-Move MCTS with Opponent Models, plus the Pommerman benchmark
context). v1 cast this as a "rollout-based candidate refiner" which is
strictly weaker than the canonical SM-MCTS + Progressive Widening + FPU
approach in the literature for our exact setting (n-player general-sum
simultaneous-move with combinatorial action space). v2 adopts the literature
algorithms as the core, with adaptations for our compute budget.

Companion to `mcts_forward_model_design.md` (the forward-model spec) and
`2026-05-05-mcts-path-a-c-kickoff.md` (the kickoff brief that scoped Path
A + Path C).

## 0. What this document does

The simulator is byte-faithful to env (all four gates at 100%). What's
missing is the **search algorithm** that uses the simulator to choose
better actions than the heuristic. This doc designs that algorithm.

Critical perf reality from `tools.sim_perf_probe` (2026-05-06):
- `Simulator.step()` = **1.77ms** per call (mid-game state, 28 planets, 5 fleets)
- 700ms turn budget (env actTimeout=1s, save 300ms for overhead)
- → **~400 sim calls per turn**
- At depth 10 rollouts: **~40 rollouts/turn**

This is two orders of magnitude below "classic" MCTS budgets (10K+ in chess).
The literature handles this exact regime via three combined techniques (per
Aljabasini 2021 §2.1.1-2.1.2):
1. **Progressive Widening (PW)** — at each node consider only `k = ⌈C·n^α⌉`
   actions, sorted by a heuristic move-ordering function. Grows wider with
   visits. Replaces "all valid actions" with "top-k by heuristic value".
2. **First-Play Urgency (FPU)** — unvisited actions get UCB value `c`
   (constant, not ∞). Critical for shallow regimes where most actions don't
   even get one visit.
3. **Decoupled UCT for simultaneous-move** — each player at each node
   independently picks `argmax UCB_i` over their own visit/value statistics.
   Joint action drives the simulator's `step()`.

Combined, these enable real SM-MCTS tree search even at our budget — with
~140 iterations per turn (using heuristic value at leaf, no rollout) we can
grow a tree of ~50-100 nodes deep across 4-5 levels with stable per-action
UCB statistics.

(v1 of this doc cast the algorithm as a "rollout-based candidate refiner"
which is essentially SM-MCTS with PW where `α=0` (constant k) and depth=1
above root. The literature approach is a strict generalization with better
opponent modeling, deeper search, and progressive exploration.)

## 1. Goal

Produce `src/orbit_wars/mcts/agent.py` exposing `mcts_agent(obs, config) -> action_list`
that:
- Beats the current heuristic agent (v1.5G + Plan A BEST) on the Kaggle ladder
  by ≥ +50 μ (the noise band per CLAUDE.md ladder note).
- Returns within 1s actTimeout on Kaggle's CPU.
- Falls back to the heuristic agent gracefully when MCTS would risk a worse
  decision (low-confidence rollout outcomes, time pressure).

**Definition of done:** ≥3 consecutive Kaggle submissions show ladder μ
≥ best_heuristic + 50, with no degradation in 100-seed local sparring vs
the existing opponent panel.

## 2. Why MCTS over alternatives

| Alternative | Why not |
|---|---|
| Pure deeper heuristic search | Heuristic's value function is its weakness, not depth. Adding more lookahead in the heuristic still uses the heuristic's evaluation — no improvement. |
| Imitation learning from top replays | Requires training infrastructure + dataset curation. ~3 weeks of work for a frame-of-reference baseline that may not even beat heuristic + Plan A. |
| Full reinforcement learning (PPO, etc.) | 50+ days of training compute, brittle to env changes. Out of scope for the deadline. |
| Alpha-beta with heuristic eval | 4P FFA breaks the minimax assumption (no clean two-player zero-sum). Implementable but no clear advantage over MCTS. |

MCTS uses the heuristic as a prior policy AND as a value function (rollout
returns), so it directly improves on what we already have. Compute requirement
is 1 sec/turn — no offline training.

## 3. Architecture (v2 — SM-MCTS + PW + FPU)

### 3.1 Core algorithm — pseudocode

Per Aljabasini 2021 Algorithm 3 (Simultaneous-Move MCTS) with Algorithm 2
(Progressive Widening) per player and FPU for unvisited actions. Decoupled
UCT means each player at each node has independent visit/value stats and
selects independently — joint action drives the simulator step.

```
SMMCTS(node, depth=0):
    # Leaf condition — heuristic value backup, NOT rollout (faster + lower variance)
    if node.is_terminal or depth == MAX_DEPTH:
        return value_estimate(node.state)

    # Per-player Progressive Widening + decoupled UCB selection
    joint_action = {}
    for player_id in alive_players(node.state):
        sorted_actions = ranked_actions_for(node.state, player_id)  # heuristic-ordered
        n_visits = node.player_visits[player_id]
        k = ceil(WIDEN_C * n_visits ** WIDEN_ALPHA)                # PW
        considered = sorted_actions[:k]
        joint_action[player_id] = ucb_select(node, player_id, considered)
                                   # uses FPU_C for unvisited; UCB1 otherwise

    # Step + recurse (or expand if new joint action)
    next_state = simulator.step(node.state, joint_action)
    if joint_action not in node.children:
        child = node.add_child(joint_action, next_state)
        v = value_estimate(next_state)              # one-step expansion
    else:
        child = node.children[joint_action]
        v = SMMCTS(child, depth + 1)                # recurse

    backpropagate(node, joint_action, v)
    return v
```

Per turn: budget loop calling `SMMCTS(root)` until time exhausted, then
return the action `argmax(visits)` for our player at the root (**robust
child** selection — most-visited action, not highest-mean-value, is more
stable per the literature).

### 3.2 Move ordering function (the heuristic-derived `f`)

PW needs `f(state, player) → ranked list of actions` to know which to
consider first. For Orbit Wars, we have an excellent move ordering signal
already: the heuristic agent's per-launch scoring in
`src/orbit_wars/heuristic/strategy.py:_decide_with_decisions`.

For each player at state S:
- Run a perspective-shifted version of `_decide_with_decisions` with
  `view.player = player_id`
- Returns a `LaunchDecision` ranked list (already sorted by score)
- Map each LaunchDecision to a discrete action token: `(planet_id, target_id, ship_fraction_bucket)`
- Add a "no launch" baseline action with score = "value of holding" estimate

Ship fractions discretized: `{ALL, 75%, 50%, 25%, MIN_LAUNCH}` — 5 buckets.
With ~6 owned planets × ~5 candidate targets × 5 fractions ≈ 150 actions,
PW reduces this to `k = ceil(2 * n^0.5)` → at n=1 visit `k=2`, at n=100
visits `k=20`. The heuristic ranking ensures the first `k` are the most
promising.

### 3.3 Value estimate at leaf — heuristic, NOT rollout

v1 used Monte Carlo rollouts to depth D. v2 uses **direct heuristic
evaluation at the leaf** instead. Rationale:

- Rollout to depth 10 = ~17ms (10 sim steps × 1.77ms). Heuristic eval ≈ 5ms.
  Heuristic is ~3× faster per leaf.
- Rollouts have high variance (different random opponent picks each time).
  Heuristic eval is deterministic for the same state.
- For the same time budget, heuristic-leaf gives ~3× more SM-MCTS
  iterations, which means deeper / wider tree growth.
- Per the thesis, AlphaZero-style "no rollout, NN value at leaf" works
  better than rollouts in many sequential-decision settings.

The `value_estimate(state, player)` function:
- If `state.terminal`: return env reward (+1 / -1)
- Else: compute `assets(player) / sum(assets(p) for p in alive_players(state))`
  with a heuristic-bonus for "good positional features" (uncontested planets,
  forward production, defense margin). Range `[0, 1]` for our player; for
  decoupled UCT each player evaluates from their own perspective.

### 3.4 Opponent modeling — symmetric heuristic move-ordering

The thesis's contribution is a learned CNN+LSTM+attention opponent model.
We can't replicate that without offline ML infra. Instead we use the
**symmetric heuristic assumption**:

> "Opponent player i picks actions per the same heuristic as we do, just
> with `view.player = i`."

Justification for Kaggle ladder:
- Most ladder agents are heuristic-derived (random, starter, hand-coded
  competitive_sniper, our own historical configs in the archive). The
  symmetric heuristic is a reasonable prior for these.
- For top-agent opponents that play differently, our PW + UCB will explore
  alternative actions over many visits and find a better estimate.
- This is strictly better than the v1 "lightweight greedy" assumption
  which was even cruder.

In code: `ranked_actions_for(state, opponent_id)` calls
`_decide_with_decisions(state, cfg, view_player=opponent_id)` and treats
the result as the heuristic ranking. All players use the same code path —
it's literally the same function with a perspective parameter.

### 3.5 Constants (initial values; tunable in M3)

| Constant | Value | Notes |
|---|---|---|
| `WIDEN_C` | 2 | base actions considered at first visit |
| `WIDEN_ALPHA` | 0.5 | sqrt growth — Pommerman benchmark default |
| `FPU_C` | 0.5 | UCB value for unvisited (vs ∞ in vanilla); 1/n_players also reasonable |
| `UCB_C` | √2 ≈ 1.41 | exploration constant |
| `MAX_DEPTH` | 5 | max tree depth (lookahead horizon) |
| `MAX_ITERATIONS` | dynamic | bounded by time budget, not a fixed N |

### 3.6 Time budget management

Per turn (700ms total = 1000ms actTimeout - 300ms safety):

| Phase | Budget |
|---|---|
| State extraction + root setup (heuristic ranking for our player) | ~50ms |
| SM-MCTS iteration loop (until 50ms remaining) | ~600ms |
| Per iteration: PW + UCB (microseconds) + 1 sim step (1.77ms) + heuristic eval at expansion (5ms) | ~7ms/iter typical, deeper tree paths add sim-step cost |
| Final pick (robust child = argmax visits at root for our player) | <5ms |

Realistic iterations per turn: **~80-100** at depth ≤ 5. A tree with 100
iterations grows ~30-50 nodes (limited by PW). Each root action gets
maybe 10-20 visits — enough for stable UCB ranking even with FPU bootstrap.

**Time-pressure mitigations:**

1. **Iteration budget check** every ~50 iterations: if time exhausted, exit
   loop and return current best action.
2. **MAX_DEPTH soft limit**: tree can grow deeper if it wants, but we cap
   at 5 to keep iteration cost bounded.
3. **Always-safe fallback**: if tree has zero visits (catastrophic timeout
   on the very first iteration), fall back to heuristic.

### 3.7 Integration with main.py

```python
# src/main.py
from orbit_wars.heuristic.strategy import agent as heuristic_agent
from orbit_wars.mcts.agent import mcts_agent, MCTSConfig

_MCTS_CFG = MCTSConfig(
    enabled=True,                 # toggleable; off → heuristic only
    candidates_k=5,
    rollouts_per_candidate=8,
    rollout_depth=10,
    fallback_threshold_ms=200,    # if <200ms left after candidate proposal, skip MCTS
    max_rollout_ms=25,
)


def agent(obs, config=None):
    if not _MCTS_CFG.enabled:
        return heuristic_agent(obs, config)
    try:
        return mcts_agent(obs, _MCTS_CFG, fallback_to_heuristic=heuristic_agent)
    except Exception:
        # Never crash on Kaggle — heuristic is the safety net.
        return heuristic_agent(obs, config)
```

**Always-safe fallback** — if MCTS errors or runs out of time, the heuristic
is invoked. The agent never returns invalid output to env.

## 4. Implementation phases (v2)

Each phase has a measurable success gate. Stop early if any phase fails its gate.

### Phase M1: Skeleton + null-MCTS baseline (Day 1)

- Create `src/orbit_wars/mcts/` package
- Add `MCTSConfig` dataclass with all constants from §3.5
- Implement `mcts_agent(obs, config)` with `enabled=False` (just delegates
  to heuristic)
- Wire into `main.py` behind the toggle
- Submit to Kaggle ladder

**Gate:** Kaggle ladder μ within ±20 of current heuristic baseline (no
regression from the wrapper itself). Validates plumbing only.

### Phase M2: Bare SM-MCTS (no PW, no FPU yet) (Day 2-3)

- Implement `MCTSNode` dataclass (per-player visit/value stats, children dict)
- Implement `extract_state_from_obs` (sibling to `extract_state_and_actions`
  for live obs; reuses `_env_dict_to_simstate`)
- Implement `ranked_actions_for(state, player)` — perspective-shifted
  heuristic ranking; output is list of discrete action tokens
- Implement `value_estimate(state, player)` — asset-count proxy at this stage
  (heuristic-eval at leaf moves to M4)
- Implement bare SM-MCTS with **fixed k = 8 considered actions per player**
  (no PW yet) and standard UCB1 (no FPU yet — unvisited gets ∞)
- 50-iteration budget per turn; depth limit 3
- Local 100-seed test vs heuristic baseline
- Kaggle submission

**Gate:** Local self-play winrate ≥ 50% vs heuristic baseline. Kaggle ladder
μ ≥ heuristic - 20 (no significant regression). If we regress significantly,
SM-MCTS isn't helping at our budget — debug ranking quality and value
estimate before adding more machinery.

### Phase M3: Add Progressive Widening + FPU (Day 4-5)

- Replace fixed `k=8` with `k = ⌈WIDEN_C · n^WIDEN_ALPHA⌉` (initial values
  from §3.5)
- Replace UCB1 unvisited=∞ with FPU constant `c=FPU_C`
- Add **robust child** selection at root (argmax visits, not value)
- Add iteration budget loop bounded by time (not fixed N)
- Local 100-seed test
- Kaggle submission

**Gate:** Kaggle ladder μ ≥ heuristic + 30. PW + FPU should help
exploration vs pure UCB1.

### Phase M4: Heuristic value at leaf (Day 6-7)

- Replace asset-count proxy with `heuristic_eval_state(state, player)` —
  full heuristic threat/opportunity scoring at leaves
- Slower per-leaf (~5ms vs ~0.05ms for asset proxy) but lower variance →
  fewer iterations needed for same statistical significance
- Tune `MAX_DEPTH` (might want shallower since each leaf is more expensive
  but more accurate)
- Local A/B vs M3 (proxy vs heuristic-eval, same iteration budget)
- Kaggle submission

**Gate:** Kaggle ladder μ ≥ heuristic + 50 (the project target).

### Phase M5 (stretch): Numba/Cython on hot paths

If M4 lands within target, the next leverage is more iterations. Profile
shows 1.77ms per `Simulator.step()` is the bottleneck. Numba JIT on the
swept-pair check + planet rotation could give 5-20× speedup → 500-2000
iterations per turn → much deeper tree.

**Gate:** Kaggle ladder μ ≥ heuristic + 100 (significant lift; closes
half the gap to top-agent territory).

## 5. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Lightweight greedy rollout policy is too unrealistic | High — biases value estimates | Phase M2 should compare value estimates against ground truth (e.g., ladder outcomes for selected actions). If MCTS picks consistently overrate moves that lose on the ladder, swap rollout policy for a partial heuristic call. |
| Asset count proxy doesn't correlate with win | Medium | Phase M3's gate forces a check — if M3 underperforms, M4 swaps to heuristic value. |
| 1.77ms per step is too slow | Medium-high | Phase M5 (Numba). Worst case: ship MCTS with depth 5 instead of 10, lose some accuracy but still some lift. |
| MCTS makes a confidently-wrong pick | High — could cost ladder μ | Always-safe heuristic fallback (Section 3.5). Plus the M2 gate (no regression vs heuristic baseline) catches this before deeper investment. |
| Submission slot scarcity (3/day) | Medium | Each phase = 1 submission. 5 phases = ~5 days minimum to validate the full design on the ladder. Plan accordingly. |
| Heuristic candidate proposal misses the genuinely best move | Medium | Future work: introduce a "wildcard" candidate that randomly explores beyond heuristic suggestions. Not in scope for v1. |

## 6. What's deliberately NOT in v1 (now v2)

- **Tree growth across turns**: each turn rebuilds the tree from scratch.
  Persistent tree + state-action mapping across turns adds complexity for
  unclear value at our budget. Revisit if M5 unlocks 10×+ iteration counts.
- **Learned opponent model (CNN+LSTM+attention)**: the thesis's main
  contribution. Requires offline ML infrastructure we don't have. We use
  symmetric heuristic instead (§3.4).
- **State-Dependent PW (SDPW)** (the thesis's Algorithm 4): makes `α`
  vary by per-opponent influence estimate. Needs the learned attention
  model to estimate influence. Skip; use fixed `α` per §3.5.
- **PUCT prior** (AlphaZero-style learned policy modulating UCB): would
  need a neural-net-trained policy. Heuristic ranking is our prior instead.
- **Move pruning by reachability**: already done by the heuristic ranking
  (since `path_collision_predicted` filters unreachable launches before
  scoring). Free win at the move-ordering level.
- **Paranoid Search** (single-coalition opponent assumption that enables
  alpha-beta-style pruning): the thesis flags it as overly pessimistic;
  decoupled UCT is more accurate. Skip.
- **Best Reply Search (BRS / BRS+)**: alternative to decoupled UCT where
  only one opponent's action varies per node. Less accurate for general-
  sum games. Skip.

## 7. Open design questions

1. **Should rollouts use deterministic `rollout_policy` or sampled?**
   Deterministic gives reproducible value estimates per candidate (less
   variance per rollout, but fewer effective samples). Sampled introduces
   variance but explores more state distributions. Phase M2 should
   measure both.
2. **How to extract state from obs efficiently?** `validator.extract_state_and_actions`
   reads from `env.steps[i][0].observation` (post-step state). For live
   agent decisions, we have `obs` directly (Struct or dict). Likely just
   need a thin wrapper around `_env_dict_to_simstate`.
3. **What does "candidate" look like exactly?** A full `list[list[float|int]]`
   of moves submitted to env? Or a more abstract `LaunchPlan` that
   `mcts_agent` materializes at decision time? Phase M2 design choice.

## 8. Cross-references

- **Aljabasini, O. (2021).** *Guiding Simultaneous Move Monte Carlo Tree
  Search via Opponent Models.* Master's thesis, TU/e. PDF in
  `docs/research_documents/mcts/`. Source for canonical algorithms
  (SM-MCTS / PW / FPU / decoupled UCT) used in this design.
- *Monte Carlo Tree Search with Velocity Object* — also in
  `docs/research_documents/mcts/`. Motion planning context; relevant for
  the heuristic value-at-leaf approach.
- `mcts_forward_model_design.md` — the simulator that MCTS uses.
- `2026-05-05-mcts-path-a-c-kickoff.md` — kickoff brief; this doc closes
  the open Path C "Section 5: MCTS algorithm itself" item.
- `src/orbit_wars/sim/simulator.py` — the simulator (1.77ms per step,
  byte-faithful to env master commit 6458c31).
- `src/orbit_wars/heuristic/strategy.py:_decide_with_decisions` — the
  move-ordering source `f` for Progressive Widening.
- `src/main.py` — the integration point.
- `tools.sim_perf_probe` — perf benchmark.
- CLAUDE.md `c_env_simulator_pivot.md` memory — the historical Path C-env
  perf finding that ruled out env-as-simulator.

## 9. Decision after Plan A lands

Once Plan A's BEST is known and submitted to ladder:
- If Plan A lifts heuristic to ladder μ ≥ 800: MCTS adds marginal value.
  Still worth doing for further lift, but consider if the extra ~5 days
  are better spent on other improvements (e.g., 4P-aware heuristic features).
- If Plan A underperforms (μ stays ≤ 700): MCTS becomes more important.
  The heuristic isn't getting better via tuning; we need fundamentally
  better decisions. Push hard on M2-M5.
