# Path-collision instrumentation report (Phase 2 step 3a)

**Date:** 2026-05-01
**Seeds:** 50 self-play episodes (v1.5G vs v1.5G, default HeuristicConfig).
**Tool:** `tools.path_collision_instrumentation`. Patches `orbit_wars.heuristic.strategy.path_collision_predicted` to log every call without modifying production code.

## Summary

- **Total calls:** 93,472
- **Total aborts:** 5,733
- **Overall abort rate:** 6.13%
- **Aborts per game:** mean 114.7, median 88, p25 47, p75 158
- **Calls per game:** median 1890

### Counterfactual rollout (would the fleet have actually been intercepted?)

- **Aborts evaluated:** 5,733 (of 5,733 total; 0 unevaluated because game ended mid-rollout)
- **True positives** (real interception would have occurred): 5,714
- **False positives** (no real interception — abort was unnecessary): 19
- **False-positive rate:** 0.3%

## Per-game distribution

| seed | calls | aborts | abort % |
|---|---|---|---|
| 0 | 1838 | 66 | 3.6% |
| 1 | 3132 | 158 | 5.0% |
| 2 | 1536 | 86 | 5.6% |
| 3 | 3698 | 271 | 7.3% |
| 4 | 1849 | 125 | 6.8% |
| 5 | 3338 | 240 | 7.2% |
| 6 | 284 | 6 | 2.1% |
| 7 | 1140 | 32 | 2.8% |
| 8 | 1360 | 28 | 2.1% |
| 9 | 3482 | 190 | 5.5% |
| 10 | 263 | 10 | 3.8% |
| 11 | 2111 | 102 | 4.8% |
| 12 | 1936 | 64 | 3.3% |
| 13 | 2196 | 216 | 9.8% |
| 14 | 1249 | 71 | 5.7% |
| 15 | 1583 | 86 | 5.4% |
| 16 | 1958 | 86 | 4.4% |
| 17 | 2237 | 140 | 6.3% |
| 18 | 2607 | 102 | 3.9% |
| 19 | 900 | 41 | 4.6% |
| … | … | … | (showing first 20 of 50) |

## Aborts by turn-bucket

| Bucket | Aborts | % of total |
|---|---|---|
| early (1-50) | 222 | 3.9% |
| mid (51-200) | 2084 | 36.4% |
| late (201-400) | 2075 | 36.2% |
| endgame (401+) | 1352 | 23.6% |

## Top obstructor planets (by abort count)

| Planet ID | Aborts caused |
|---|---|
| 14 | 483 |
| 13 | 454 |
| 23 | 362 |
| 20 | 348 |
| 21 | 329 |
| 12 | 313 |
| 22 | 302 |
| 15 | 294 |
| 19 | 233 |
| 16 | 233 |

## Obstructor by owner

| Owner | Aborts caused | Note |
|---|---|---|
| 1 | 2608 | enemy 1 |
| 0 | 2595 | self (player 0) |
| -1 | 530 | neutral |

## Interpretation and decision

Per Phase 2 spec decision tree:
- If aborts are **rare** (≪1 per game median) AND patterns suggest the check is doing useful work: close the loop, no 3b needed.
- If aborts are **frequent** (many per game) AND a high fraction look like false positives (predicted collision against planets that wouldn't realistically intercept): 3a data justifies a 3b hot-fix proposal to add a `relax_path_collision` toggle and ladder-test it.

**This pass added counterfactual rollouts** (using each game's recorded `env.steps` to check whether the virtual fleet would have actually been intercepted by any planet's true post-turn position). 5,714 of 5,733 aborts were true positives — the predicted collision would have actually happened in the real env trajectory. Only 19 aborts were false positives.

**Decision: CLOSE THE LOOP. No 3b hot-fix needed.**

Aborts are not rare (median 88/game), but the FP rate is **0.3%** — overwhelmingly the check is preventing real interceptions. The launch behavior `path_collision_predicted` enforces is consistent with the env's actual physics (env phase 6: fleets collide with any planet on their path).

**Implications beyond Step 3a:**

1. Phase 1 synthesis's "peers with weaker path-clearance score higher" finding (TL;DR #2) is NOT explained by v1.5G's path-collision check being over-conservative. The peers' apparent edge — if real and not noise — must come from elsewhere (better fleet sizing, better target selection, better economy/defense balance, or simply ladder noise that happened to favor them when their submissions were measured).
2. The user's replay observation #3 (skipping nearby targets to chase distant whales) is NOT explained by path-collision aborts. Of three hypotheses posed during initial discussion — (a) small-fleet slowness from log-1.5 speed curve interacting with moving targets, (b) `min_launch=20` floor blocking small targets, (c) path-collision rejecting close paths — hypotheses (b) and (c) are both eliminated. Only (a) survives as a candidate explanation.
3. The fleet-sizing / fleet-speed connection is therefore the more promising direction for the user's replay-based observations 1 and 3. Step 4 (multi-source pincer) could plausibly be expanded to include the fleet-sizing changes (track inbound_enemy on contested neutrals, speed-optimal-send sizing) that address observations 1 and 2 directly.

## Raw data

Full per-abort log + per-game counts in JSON: see sibling file `path_collision_instrumentation.json`.
