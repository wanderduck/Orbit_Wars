---
source_url: https://www.kaggle.com/code/mdmahfuzsumon/how-my-ai-wins-space-wars
author: mdmahfuzsumon
slug: how-my-ai-wins-space-wars
title_claim: "Orbit Wars AI -- The Strategic Mind"
ladder_verified: rank 498, score 796.8
pulled_on: 2026-05-01
pull_command: uv run kaggle kernels pull mdmahfuzsumon/how-my-ai-wins-space-wars
---

# mdmahfuzsumon/how-my-ai-wins-space-wars

## Architecture in one sentence
A four-phase rule-based agent (greedy single-source -> two-planet pincer -> opportunistic secondary -> frontline reinforcement) using sun-avoidance via tangent waypoints, iterative aim prediction for orbiting/comet targets, and a small opponent-aggression heuristic that scales defense reserves.

## Notable techniques
- **Sun-avoidance via lateral waypoints**: when a direct segment hits the sun (with `SUN_SAFETY=1.5`), `safe_angle_and_distance` tries lateral offsets at `2x/3x/4x` sun radius on both sides and routes through the cheapest viable waypoint (cell 1).
- **Coordinated two-planet attack** (`find_coordinated_sources`, cell 1): if no single planet can muster `needed`, it pairs the nearest source with one partner that can cover the deficit; both fleets are launched same turn but no arrival-time matching.
- **Map-control bonus**: `map_control_bonus` multiplies target value by 1.4 within 20 of center, 1.2 within 35 (cell 1) -- crude positional weighting that v1.5G lacks.
- **Strategic blocking**: `enemy_is_targeting` boosts a target's value by 1.4 if any enemy fleet's heading vector projects toward it (cell 1).
- **Opponent-aggression scaling**: ratio of enemy ships in flight vs garrisoned; if >0.5, defense reserves are multiplied by 1.5 (cell 1).
- **Multi-event garrison simulator** (`simulate_planet_outcome`, cell 1): groups arrivals by turn, applies "largest minus second-largest" combat at each event, accrues production between events.

## Visible evidence
Phase-1 candidate scoring (cell 1):
```python
value = target_value(tgt, turns)
cost = ships_needed + turns * 0.6
score = value / (cost + 1.0)
if is_early and tgt.owner == -1 and ships_needed <= 15:
    score *= 1.5
candidates.append((score, src.id, tgt.id, angle, ships_needed, turns))
```
Coordinated launch (cell 1):
```python
coord = find_coordinated_sources(tgt, my_planets, available, needed,
                                  best_src.id, initial_by_id, ang_vel,
                                  comets, comet_ids)
```

## Relevance to v1.5G (note: this author scores ABOVE our agent -- be especially attentive)
- **Path-collision check is weaker than ours**: only checks 3-unit step away from source via `segment_hits_sun`; no full path-integration vs moving planets like `path_collision_predicted`. Author still scores ~796 -- suggests the marginal benefit of full path-clearance may be smaller than assumed.
- **Map-control bonus** (1.4x near center) is a one-line heuristic that v1.5G has no analogue for. Worth A/B-testing against our priority function.
- **Defense scaling by opponent aggression** (1.0 vs 1.5 multiplier) is simpler than our `WorldModel.base_timeline` forecast; their defense is reactive (current-turn arrivals only) but the aggression gate is novel.
- **Two-planet pincer with no arrival synchronization** -- multi-source coordination explicitly noted as a v1.5G gap. Their version doesn't time-match arrivals, just sums ships at the target. Cheap hack worth considering before full swarm logic.
- **Cost penalizes turn count** (`+ turns*0.6`) -- our greedy is purely nearest-target; weighting nearby targets explicitly may be net positive.

## What couldn't be determined
- No tournament evidence in the notebook -- author only writes `submission.py`, never runs it.
- No tuning history; constants (1.4, 1.5x, 0.6 turn-cost weight) are unjustified.
- `fleet_speed` uses `log(1000.0)` denominator and `MAX_SPEED=6.0` -- matches our understanding but no source attribution.
