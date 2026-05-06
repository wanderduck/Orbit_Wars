# MCTS algorithm design — 2026-05-06

**Status:** draft. Authored after the Plan C simulator complete + env upgrade
to master (commit 6458c31). Companion to `mcts_forward_model_design.md` (the
forward-model spec) and `2026-05-05-mcts-path-a-c-kickoff.md` (the kickoff
brief that scoped Path A + Path C).

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
The design must therefore lean heavily on:
1. **Strong heuristic prior** — don't waste rollouts on obvious garbage
2. **Aggressive action pruning** — reduce branching factor before search
3. **Shallow rollouts with heuristic value backup** — depth 5-10 max, use
   a value estimate at the leaf rather than terminal-state simulation

Cast the algorithm as a **rollout-based candidate refiner**, not a from-scratch
tree search. Heuristic proposes top-K candidates; MCTS does N rollouts per
candidate to pick the best.

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

## 3. Architecture

### 3.1 High-level flow per turn

```
mcts_agent(obs):
    state ← extract_state_from_obs(obs)
    candidates ← heuristic_propose_top_k(state, K=5)   # heuristic-driven action shortlist
    if len(candidates) ≤ 1:
        return candidates[0] or []                     # nothing to refine
    if time_remaining() < SAFE_FALLBACK_MS:
        return heuristic_pick_best(candidates)         # don't risk a bad rollout
    rollout_budget ← compute_per_candidate_budget()    # ~8 rollouts per candidate
    for c in candidates:
        c.value ← mean_rollout_return(state, c, rollout_budget)
    chosen ← argmax(c.value over candidates)
    return chosen.action_list
```

This is **NOT** a UCT tree. It's a **rollout-based shortlist refinement**.
We don't grow a search tree across turns; each turn does fresh evaluations
of K candidates from a single state.

### 3.2 Action proposal — the K candidates

Action space is huge — every turn each owned planet can launch any number
of ships at any continuous angle. Direct enumeration is infeasible.

**Heuristic-driven proposal** (re-uses existing planning code):

The current heuristic in `src/orbit_wars/heuristic/strategy.py:_decide_with_decisions`
already produces ranked launch decisions per planet. We extend it to return
the **top-K full action lists** (not just the best one):

| Candidate generation strategy | Notes |
|---|---|
| 1. Greedy-best (heuristic's current top-1) | The agent's existing pick — baseline for "do at least as well" |
| 2. Top-K alternative target assignments | Take the next K-1 best target choices from `_plan_offense_greedy` / Hungarian |
| 3. "Hold" variant | Don't launch this turn — useful when defense is prioritized and we want to bank ships |
| 4. Aggressive pincer | Launch 2 fleets from different planets at the same target — heuristic sometimes misses this |
| 5. Comet attack variant | Force-include a comet target if reachable (heuristic underweights comets per the user's replay observations) |

K=5 is the working number. With ~400 sim budget total and depth-10 rollouts,
that's ~8 rollouts per candidate. Tight but workable.

### 3.3 Per-candidate rollout

```
rollout(state, candidate_action, depth):
    s ← simulator.step(state, {our_player: candidate_action,
                                **opponent_actions(state)})
    for t in 1..depth-1:
        actions ← {p: rollout_policy(s, p) for p in alive_players(s)}
        s ← simulator.step(s, actions)
    return value_estimate(s, our_player)
```

Three subcomponents to design:

#### 3.3.1 `rollout_policy(state, player)`

What action does player `p` take at depth `t > 0`? Options:

- **Heuristic**: re-run `heuristic.decide()` for player `p`. Most accurate
  but expensive — heuristic decision time is ~10-20ms which would crush our
  budget. **Reject** for inner-loop use.
- **Random launches**: pick a random owned planet, random angle, random
  ship count. Fast but noisy; pure-random doesn't approximate top-agent
  behavior at all.
- **Lightweight greedy** (chosen): for each owned planet, with probability
  `LAUNCH_RATE = 0.3`, launch the largest possible fleet at the nearest
  enemy planet. Otherwise hold. Cost: ~50µs per player per turn. Provides
  a "minimally competent" baseline opponent in the rollout.

The lightweight greedy approximates what a casual heuristic might do.
Top-agent strategies aren't replicated, but the SHAPE of competing for
planets and fleet attrition is preserved.

#### 3.3.2 `value_estimate(state, player)`

At the end of the rollout (depth = D), evaluate the state from `player`'s
perspective. Options:

- **Final reward only** (game ended via win/loss): use the env reward
  +1/-1 if game has terminated by depth D. Otherwise use…
- **Asset count proxy** (chosen): sum of `player`'s owned planet ships +
  in-flight fleet ships, normalized by total assets across all alive
  players. Range [0, 1]; 1 = player owns all assets, 0 = player eliminated.
  Cost: ~10µs.
- **Heuristic eval** at leaf: re-run the heuristic's threat/opportunity
  scoring on the leaf state. More accurate but adds ~5ms per leaf — cuts
  rollout count by 2-3x. **Defer to v2** of MCTS if rollouts-only doesn't
  beat heuristic.

The asset count proxy correlates well with game outcome (the env's win
condition is "outlast all opponents", which usually traces to asset
dominance). It's noisy on a per-rollout basis but averages out across
the candidate's N rollouts.

#### 3.3.3 `opponent_actions(state)`

What actions do enemies take at depth 0 (the immediate next step)?

For 4P games this is the hardest design decision. Three approaches:

| Approach | Pros | Cons |
|---|---|---|
| **Assume null actions** | Fast (no opp simulation). Conservative — assumes enemies don't react. | Wildly inaccurate on the ladder where opps actively contest us. |
| **Run heuristic for each opp** | Most accurate. | ~20ms × 3 opponents = 60ms per rollout STEP. Kills budget. |
| **Lightweight greedy for each opp** | Fast (~50µs × 3 opp = 150µs). Reasonable assumption. | Underestimates clever opponents; likely overestimates random opponents. |

**Chosen: lightweight greedy for opponents** — same `rollout_policy`
applied to each non-self player. This makes the rollout self-consistent
(all non-actor players use the same decision rule) and keeps budget
manageable.

Risk: if the ladder has opponents that play very differently from
"lightweight greedy", our value estimates are biased. Mitigation:
post-launch, compare MCTS picks against heuristic picks and measure
ladder μ delta — if MCTS underperforms, increase opponent fidelity.

### 3.4 Time budget management

Per-turn budget breakdown (700ms total to leave 300ms safety margin):

| Phase | Budget |
|---|---|
| State extraction + heuristic candidate proposal | ~100ms (heuristic decide is ~10-20ms; doing K=5 variants ~50-100ms) |
| Per-candidate rollouts (5 candidates × 8 rollouts × 10 depth) | ~500ms (1.77ms × 5 × 8 × 10 = 708ms — TOO TIGHT, see mitigations) |
| Final pick + return | <10ms |

**Mitigations for the tight rollout budget:**

1. **Adaptive depth**: start at depth 10; if remaining budget tight, drop
   to depth 5 with heuristic value backup at leaf.
2. **Sequential elimination**: do 2 rollouts per candidate first; eliminate
   bottom 2 candidates; spend remaining budget on top 3.
3. **Time ceiling per rollout**: hard-stop a rollout if it exceeds
   `MAX_ROLLOUT_MS = 25ms` (safety against pathological state combinations).
4. **Fallback to heuristic** if budget exhausted before rollouts complete:
   return the heuristic's top-1 candidate (always-safe fallback).

### 3.5 Integration with main.py

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

## 4. Implementation phases

Each phase has a measurable success gate. Stop early if any phase fails its gate.

### Phase M1: Skeleton + null-MCTS baseline (Day 1)

- Create `src/orbit_wars/mcts/` package
- Add `MCTSConfig` dataclass
- Implement `mcts_agent` with `enabled=False` (just calls heuristic)
- Wire into `main.py` with the toggle
- Submit to Kaggle ladder

**Gate:** Kaggle ladder μ within ±20 of current heuristic baseline (no
regression from the wrapper itself).

### Phase M2: Single-rollout-per-candidate (Day 2-3)

- Implement `extract_state_from_obs` (re-uses `validator.extract_state_and_actions`
  but adapted for live obs not env.steps)
- Implement `heuristic_propose_top_k(state, K=5)`
- Implement `rollout_policy` (lightweight greedy)
- Implement `value_estimate` (asset count proxy)
- Implement `mcts_agent` with K=5 candidates × 1 rollout each at depth 10
- Local 100-seed test vs heuristic baseline
- Kaggle submission

**Gate:** Local self-play winrate ≥ 50% vs heuristic baseline. Kaggle ladder
μ ≥ heuristic baseline (no regression). If either fails, MCTS is not
helping yet — debug rollout policy / value estimate before adding complexity.

### Phase M3: Multi-rollout averaging + adaptive budget (Day 4-5)

- Implement N=8 rollouts per candidate with mean value
- Add time-budget tracking (`fallback_threshold_ms`, `max_rollout_ms`)
- Add sequential elimination (eliminate bottom 2 after 2 rollouts each)
- Local 100-seed test
- Kaggle submission

**Gate:** Kaggle ladder μ ≥ heuristic + 30 (positive lift, but small).

### Phase M4: Heuristic value at leaf (Day 6-7) — only if M3 underperforms

- Replace asset-count proxy with full heuristic-eval at leaf
- This kills rollout count (~3-4 per candidate instead of 8) but increases
  per-rollout signal quality
- Local A/B vs M3 (proxy vs heuristic-eval)
- Kaggle submission

**Gate:** Kaggle ladder μ ≥ heuristic + 50 (the project target).

### Phase M5 (stretch): Numba/Cython on hot paths

If M4 lands within target, it's likely we can squeeze 2-5x more rollouts by
JIT-compiling the simulator's Phase 4-5 (the perf hotspots). Would unlock:
- Wider candidate set (K=10 instead of 5)
- Deeper rollouts (depth 20 instead of 10)
- Or more rollouts per candidate (N=16 instead of 8)

**Gate:** Kaggle ladder μ ≥ heuristic + 100 (significant lift). If we can
afford this, it's the difference between "marginal MCTS" and "real MCTS".

## 5. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Lightweight greedy rollout policy is too unrealistic | High — biases value estimates | Phase M2 should compare value estimates against ground truth (e.g., ladder outcomes for selected actions). If MCTS picks consistently overrate moves that lose on the ladder, swap rollout policy for a partial heuristic call. |
| Asset count proxy doesn't correlate with win | Medium | Phase M3's gate forces a check — if M3 underperforms, M4 swaps to heuristic value. |
| 1.77ms per step is too slow | Medium-high | Phase M5 (Numba). Worst case: ship MCTS with depth 5 instead of 10, lose some accuracy but still some lift. |
| MCTS makes a confidently-wrong pick | High — could cost ladder μ | Always-safe heuristic fallback (Section 3.5). Plus the M2 gate (no regression vs heuristic baseline) catches this before deeper investment. |
| Submission slot scarcity (3/day) | Medium | Each phase = 1 submission. 5 phases = ~5 days minimum to validate the full design on the ladder. Plan accordingly. |
| Heuristic candidate proposal misses the genuinely best move | Medium | Future work: introduce a "wildcard" candidate that randomly explores beyond heuristic suggestions. Not in scope for v1. |

## 6. What's deliberately NOT in v1

- **Tree growth across turns**: each turn does a fresh shortlist evaluation;
  no persistent tree. Adds complexity without obvious value at our budget.
- **Opponent modeling beyond lightweight greedy**: too expensive in pure Python.
  Revisit only if M5 perf budget permits.
- **PUCT prior**: the heuristic IS the prior (it generates the candidate
  shortlist). Adding a learned policy network would be a different project.
- **Exploration term (UCB)**: not meaningful for shortlist refinement —
  we evaluate ALL candidates each turn rather than choose which to expand.
- **Move pruning by reachability**: relies on `path_collision_predicted`
  which is now swept-pair-correct. This is a free win — pruned by the
  heuristic before MCTS sees the candidate.

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

- `mcts_forward_model_design.md` — the simulator that MCTS uses
- `2026-05-05-mcts-path-a-c-kickoff.md` — kickoff brief; this doc closes
  the open Path C "Section 5: MCTS algorithm itself" item
- `src/orbit_wars/sim/simulator.py` — the simulator (1.77ms per step,
  byte-faithful to env master commit 6458c31)
- `src/orbit_wars/heuristic/strategy.py:_decide_with_decisions` — the
  candidate-generation source for top-K proposals
- `src/main.py` — the integration point
- `tools.sim_perf_probe` — perf benchmark
- CLAUDE.md `c_env_simulator_pivot.md` memory — the historical Path C-env
  perf finding that ruled out env-as-simulator

## 9. Decision after Plan A lands

Once Plan A's BEST is known and submitted to ladder:
- If Plan A lifts heuristic to ladder μ ≥ 800: MCTS adds marginal value.
  Still worth doing for further lift, but consider if the extra ~5 days
  are better spent on other improvements (e.g., 4P-aware heuristic features).
- If Plan A underperforms (μ stays ≤ 700): MCTS becomes more important.
  The heuristic isn't getting better via tuning; we need fundamentally
  better decisions. Push hard on M2-M5.
