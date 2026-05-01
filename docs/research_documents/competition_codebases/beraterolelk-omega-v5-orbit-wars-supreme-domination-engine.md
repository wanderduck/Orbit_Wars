---
source_url: https://www.kaggle.com/code/beraterolelk/omega-v5-orbit-wars-supreme-domination-engine
author: beraterolelk
slug: omega-v5-orbit-wars-supreme-domination-engine
title_claim: '"OMEGA v5 - Orbit Wars Supreme Domination Engine" / "Target: TOP 5 Leaderboard" / "Score 1000+ Elo" (rhetorical; actual ladder 616.4)'
ladder_verified: rank 988, score 616.4
pulled_on: 2026-05-01
pull_command: uv run kaggle kernels pull beraterolelk/omega-v5-orbit-wars-supreme-domination-engine
---

# beraterolelk/omega-v5-orbit-wars-supreme-domination-engine

## Architecture in one sentence
Pure-Python heuristic agent (~2.2k LOC `submission.py` written from cell 16); a `WorldModel` builds per-planet timelines with binary-searched `keep_needed`, then ~12 mission builders (capture, counter-rush, snipe, rescue, reinforce, recap, crash, gang-up, elimination, deny, intercept) generate `ShotOption`s scored by ~14 stacked multipliers and dispatched greedily under an `actTimeout * 0.84` deadline.

## Notable techniques
- Cell 16, lines 610-645: `simulate_timeline` walks every turn to HORIZON=120 resolving "largest vs second-largest" combat, then bisects min garrison that survives all forecast arrivals. Cleaner formalisation than our base_timeline forecast.
- Cell 16, lines 430-454: `bypass_angle` builds a tangent waypoint around an inflated sun-danger circle (radius 12.4) when direct LoS is sun-blocked; returns shorter of CW/CCW route. We currently abort sun-blocked launches.
  ```python
  def bypass_angle(sx, sy, sr, tx, ty, tr, clockwise=True):
      danger_r = SUN_R + SUN_SAFETY + 0.6
      to_sun_d = dist(sx, sy, CENTER_X, CENTER_Y)
      if to_sun_d <= danger_r: return None
      base_angle = math.atan2(CENTER_Y-sy, CENTER_X-sx)
      half_ang   = math.asin(min(1.0, danger_r / to_sun_d))
      tang_angle = base_angle + (half_ang + 0.18 if clockwise else -(half_ang + 0.18))
  ```
- Cell 16, lines 384-405: `speed_optimal_send` (HYPER TSUNAMI) compares "send needed" vs "send 92% of available", recomputes fleet_speed, over-commits if the larger fleet saves >=1 turn (because prod*turns_saved ships gained for free). Direct exploit of the log-1.5 speed curve.
- Cell 16, lines 706-723 + 1447-1483: `detect_rush` projects every enemy fleet's velocity vector onto our planets; if rush detected, the highest-prod enemy planet ("home") gets score x COUNTER_RUSH_HOME_BONUS=2.00. Multi-front response we lack.
- Cell 16, lines 676-688: `detect_vulnerable_planets` flags any enemy planet that just emitted >= VULN_MIN_SENT ships totalling >= VULN_SENT_RATIO of garrison; combined with EXPOSED_VM=2.80 and VULN_WINDOW_BONUS=2.20 those targets become ~6x more attractive. We do no fleet-departure tracking.
- Cell 16, lines 754-766 + 1815-1840: 5-tier eco mode (SNOWBALL/EXPAND/BALANCED/AGGRO/PANIC) plus death-ball endgame: in last 60 turns either `defend` (drops all captures, only rescue/reinforce) or `allin`. Adaptive in a way our static HeuristicConfig is not.
- Cell 16, lines 733-753: planet triage abandons low-prod (<2) planets whose keep_needed > planet_value * 3.0; inverse of our defense-everything posture.
- Cell 16, lines 768-840: `WorldModel.__init__` centralises owner_strength, owner_prod, win_ratio, arrival ledger, per-planet timelines, vulnerable IDs, gateway map plus 4 memo dicts. Heavier than ours but cleanly factored.

## Visible evidence
None executed. Every code cell has zero `outputs` in the .ipynb JSON — the notebook was committed unrun, so all "x6.16 multiplier" / "TSUNAMI saves N turns" / validation-suite tables are inert prints, not observed behavior. The validation cell (18) defines 14 hand-crafted obs scenarios that only assert `agent(obs)` returns well-formed actions — it does NOT measure win-rate against any opponent. Only externally verifiable signal is the Kaggle ladder (616.4 / rank 988), which contradicts the "TOP 5" / "1000+ Elo" framing.

## Relevance to v1.5G
- We already have: WorldModel-style timeline projection (base_timeline + defense flip detection), late-game launch filter (their `turns > world.remaining - buf` mirrors our `EPISODE_STEPS - obs.step` cap), nearest-source assignment, intercept aim for moving/comet targets, the obs dict-or-Struct guard (their `_read` helper).
- Slot-in candidates we lack: sun-tangent bypass routing, vulnerability-window scoring, simultaneous counter-rush, eco-mode tiering, death-ball defend, planet triage, binary-search keep_needed.
- Contradicts our approach: no scipy / Hungarian assignment — pure greedy mission queue (consistent with our v1.5G greedy default); no path-collision check against intervening planets — they only guard against the sun, exposed to the "fleets collide with ANY planet on path" rule from CLAUDE.md.
- CLAUDE.md anti-pattern: module-level `_step` counter at line 2218 is exactly the "don't build a module-level counter cache to track step number" warning. As `max(obs_step, inferred_step)` it would pollute under post-hoc replays via `decide_with_decisions`.
- Empirical caveat: ~2.2k LOC of heuristic machinery and the agent ranks 988 vs our v1.5G ~655. Treat as ideation source, not gospel.

## What couldn't be determined
- Whether the OPENING_BOOK turns 1-35 phase actually triggers special logic — flag is set on WorldModel but I did not locate a dedicated branch in `plan_moves` consuming it.
- Whether `actTimeout * 0.84` leaves enough budget on Kaggle's 1s wall-clock for the heavy mission builders; no benchmarks recorded.
- Whether the multiplier stack (HOSTILE 2.40 x EXPOSED 2.80 x VULN_WINDOW 2.20 ~= 14.78x) fires together or saturates other targets out; no scoring traces.
- FFA-specific behavior beyond the `is_ffa = num_players >= 4` flag — kingmaker / alliance dynamics not visibly addressed.
