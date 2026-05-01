# E9: romantamrazov-lb1224

## Source
https://www.kaggle.com/code/romantamrazov/orbit-star-wars-lb-max-1224

## Fetch method
kaggle kernels pull (succeeded; .ipynb at /tmp/ow_e9/orbit-star-wars-lb-max-1224.ipynb, 118 KB — largest of the 5). Extracted via Python; analyzed inline. Original sub-agent dispatch failed at "You've hit your org's monthly usage limit" — orchestrator completed inline.

## Goal
**This notebook is NOT a learned model — it is a heuristic agent in the same lineage as E6 (pilkwang) and E8 (sigmaborov), but tuned further.** The slug claims a leaderboard score of **1224**, which is the highest known among the 5 reference notebooks. As of fetch time, this is the closest thing to a top-of-leaderboard reference we have.

The structural fingerprint is identical to E6/E8: same `TOTAL_STEPS = 500`, `SIM_HORIZON = 110`, `ROUTE_SEARCH_HORIZON = 60`, `simulate_planet_timeline`, `WorldModel`, `target_value`, `min_ships_to_own_by`, `aim_with_prediction`, `resolve_arrival_event`. Same constants (e.g., `STATIC_TARGET_SCORE_MULT = 1.18`, `EARLY_STATIC_NEUTRAL_SCORE_MULT = 1.25`, `FOUR_PLAYER_ROTATING_NEUTRAL_SCORE_MULT = 0.84`, `SNIPE_SCORE_MULT = 1.12`, `SWARM_SCORE_MULT = 1.06`, `CRASH_EXPLOIT_SCORE_MULT = 1.05`, `DEFENSE_FRONTIER_SCORE_MULT = 1.12`).

The notebook is **larger** than E6 (~118 KB vs E6's ~196 KB submission file but more cells in the .ipynb), suggesting either more code, more verbose comments, or more tuning experimentation cells. It contains tuning-trace comments like:

```python
TOTAL_WAR_REMAINING_TURNS = 55     # was 38 — endgame push starts sooner
```

This is the smoking gun: the author has been iterating on the constants and noted the prior value alongside the new one.

## Methods
Same 5-layer pipeline as E6/E8. Same world model, same combat resolver, same intercept solver, same mission decomposition (capture / snipe / swarm / reinforce / recapture / crash-exploit / followup). What appears to differ from E6/E8 is the **tuning regime** — values have moved, with the `# was X` comments preserving the audit trail.

Reinforcement-mission constants (line 115+ in extracted file):
```python
REINFORCE_VALUE_MULT = 1.35              # same as E8
REINFORCE_ENABLED = True
REINFORCE_MIN_PRODUCTION = 2
REINFORCE_MAX_TRAVEL_TURNS = 22
REINFORCE_SAFETY_MARGIN = 2
REINFORCE_MAX_SOURCE_FRACTION = 0.75
REINFORCE_MIN_FUTURE_TURNS = 40
REINFORCE_HOLD_LOOKAHEAD = 20            # same as E6
REINFORCE_COST_TURN_WEIGHT = 0.35
```

Endgame:
```python
TOTAL_WAR_REMAINING_TURNS = 55     # was 38 — endgame push starts sooner
```

The "total war" phase is when the agent abandons economy and pushes ships at enemies; pulling its trigger 17 turns earlier (38 → 55) means more time spent in elimination mode. This is the kind of late-game tuning that compounds with E6's `LATE_IMMEDIATE_SHIP_VALUE = 0.6` and `ELIMINATION_BONUS = 18.0` to drive ship count differential at episode end.

The function `reinforcement_needed_to_hold_until(target_id, hold_until, planned_commitments)` (line 1071+) is symmetric to E8's `reinforcement_needed_for` but parametrized over a `hold_until` deadline rather than a single `arrival_turn`. It binary-searches the minimum reinforcement that keeps the planet ours through `hold_until`. This is **subtly stronger than E8's version** — it considers the full survival window, not just survival up to a single defensive arrival.

## Numerical params / hyperparams

Constants identical to E6/E8 except where noted. Notable values from this fork's header:

```python
TOTAL_STEPS = 500
SIM_HORIZON = 110
ROUTE_SEARCH_HORIZON = 60
HORIZON = SIM_HORIZON
TOTAL_WAR_REMAINING_TURNS = 55     # was 38 — endgame push starts sooner
PROACTIVE_DEFENSE_HORIZON = 12
MULTI_ENEMY_PROACTIVE_HORIZON = 14
```

All `*_SCORE_MULT` and `*_VALUE_MULT` constants match E6 exactly (within sampled lines). Tuning deltas relative to E6 are likely concentrated in the late-game / "total war" / proactive-defense regime, plus possibly the swarm/crash thresholds.

## Reusable code patterns
See E6 report — same code lineage, same patterns. The unique addition seen so far:

### `reinforcement_needed_to_hold_until` (line 1071+)
```python
def reinforcement_needed_to_hold_until(self, target_id, hold_until, planned_commitments=None):
    ...
    def holds_with_reinforcement(ships):
        # replays timeline with `ships` extra reinforcement at `arrival_turn`,
        # checks owner_at[t] == player for all t in [arrival_turn, hold_until]
        ...
    # exponential search up to search_cap, then binary search
    if not holds_with_reinforcement(hi):
        ...
    while hi <= search_cap and not holds_with_reinforcement(hi):
        hi *= 2
    if not holds_with_reinforcement(hi):
        return None  # cannot hold
    while hi > lo:
        if holds_with_reinforcement(mid): hi = mid
        else: lo = mid + 1
    return lo
```
**Adopt this version, not E8's.** It accounts for the full hold window, which matters when multiple enemy fleets are spaced out.

## Reported leaderboard score
**1224** — per the slug `orbit-star-wars-lb-max-1224`. "lb-max" suggests this was the author's peak score (not necessarily current). This is the **highest known** among the 5 reference notebooks:

| Notebook | Approach | LB Score |
|----------|----------|----------|
| E5 (bovard getting-started) | Heuristic (sniper) | n/a (tutorial) |
| E6 (pilkwang structured baseline) | Heuristic (5-layer, v11) | n/a (no LB cited) |
| E7 (kashiwaba RL tutorial) | PPO RL | n/a (tutorial) |
| **E9 (romantamrazov)** | **Heuristic (E6 lineage, tuned)** | **1224** ← highest |
| E8 (sigmaborov lb-958) | Heuristic (E6 lineage v6) | 958.1 |

For context, E1 noted that bots start at μ₀=600 with σ uncertainty. A bot scoring 1224 is ~2σ above mean (assuming σ shrinks to ~150-200 with games played). Plausibly top-30 of 1720 teams.

## Anything novel worth replicating

Beyond E6/E8:

1. **`TOTAL_WAR_REMAINING_TURNS = 55` (vs prior 38)** — flip into endgame mode 17 turns earlier. The annotation suggests the change was deliberate and contributed to the score climb. Adopt 55 as our v1 default.
2. **`reinforcement_needed_to_hold_until` (vs E8's `reinforcement_needed_for`)** — quantifies the survival window cost more accurately. Adopt this version.
3. **Audit-trail comments (`# was X`)** — the author preserves prior values when tuning. Adopt this convention in our `HeuristicConfig` so we can track tuning history in code without git archaeology.
4. **Implication for our roadmap**: a heuristic that's been carefully tuned (per E9's evident iteration history) is a stronger baseline than a freshly-trained PPO model (per E7's clearly underdeveloped setup). **Investing v1+v2 effort in heuristic tuning may yield more leaderboard climb per hour than RL training.**
5. **`HORIZON = SIM_HORIZON` aliasing** — small refactor that suggests the author distinguishes simulation horizon from other horizons (route search, defense lookahead). Useful semantic clarity.
6. **Implicit code organization** — 3312 lines of extracted content (vs E6's much shorter dump from WebFetch) suggests this notebook ships its agent as one large `submission.py` plus more markdown commentary. Worth adopting the "one-file submission" style for our `pack` command's RL submissions in v2+ (heuristic v1 is already module-split per spec §5).

## Direct quotes / code snippets to preserve

```python
# Tuning trace — preserve this convention
TOTAL_WAR_REMAINING_TURNS = 55     # was 38 — endgame push starts sooner

# Constants (matching E6/E8 — see E6 report for full list)
REINFORCE_VALUE_MULT = 1.35
SNIPE_SCORE_MULT = 1.12
SWARM_SCORE_MULT = 1.06
CRASH_EXPLOIT_SCORE_MULT = 1.05
DEFENSE_FRONTIER_SCORE_MULT = 1.12
```

## Open questions / things I couldn't determine

- **Full diff vs E6 (pilkwang) and E8 (sigmaborov)**. Tools to do this cleanly — `diff` between extracted .py files — not run.
- **What other constants moved**. Only `TOTAL_WAR_REMAINING_TURNS` was sampled with a `# was X` comment, but there may be many more.
- **Whether this notebook ADDS missions/strategies vs E6** — the line counts suggest more code, but the constants header is structurally similar. Could be expanded markdown rather than expanded code.
- **What share of the 1224 score is attributable to (a) the tuning of E6's constants vs (b) any new mission types vs (c) opponent-pool factors** (e.g., if the author's bot mostly faced random/sniper opponents during the score window).
- **Whether 1224 was achieved in 2-player or 4-player ladder, or both**. Score is global per Kaggle's ladder.
- **When 1224 was the LB-max**. The score rises and falls; the slug is a snapshot.
- **Whether the author has open-sourced training/tuning experiments** outside this notebook (no other related notebooks listed).
- **Whether E9 includes the v6→v11 jump from E8 to E6 (pilkwang)** plus additional tuning, or whether it's an independent fork from a different version.

### Implication for our v1 heuristic

E9 ratifies E6+E8: **the leaderboard rewards a well-tuned heuristic with arrival-time forecasting, mission-based decision making, and late-game ship-count optimization.** Our v1 implementation should follow this template closely. Specifically, the `HeuristicConfig` (spec §7.2) should adopt:

- E6's full constants table as starting values
- E8's REINFORCE mission with `REINFORCE_VALUE_MULT = 1.35`
- E9's `TOTAL_WAR_REMAINING_TURNS = 55`
- E9's `reinforcement_needed_to_hold_until` (over E8's narrower variant)
- The `# was X` audit-trail comment convention for our tuning history
