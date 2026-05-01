---
source_url: https://www.kaggle.com/code/johnjanson/lb-max-score-1000-agi-is-here
author: johnjanson
slug: lb-max-score-1000-agi-is-here
title_claim: '"LB Max Score 1000 - AGI is here" (rhetorical; actual ladder: 747.8)'
ladder_verified: rank 672, score 747.8
pulled_on: 2026-05-01
pull_command: uv run kaggle kernels pull johnjanson/lb-max-score-1000-agi-is-here
---

# johnjanson/lb-max-score-1000-agi-is-here

## Architecture in one sentence
Single-cell `%%writefile submission.py` with ~1500 LOC of pure-Python heuristics: a `WorldModel` per turn that builds an arrival ledger, simulates per-planet timelines, then a `plan_moves` pipeline that proposes Mission objects (capture / snipe / swarm / 3-source-swarm / reinforce / crash-exploit / doomed-evac / rear-to-front logistics), sorts by score, and commits via shared `planned_commitments` and `spent_total` ledgers.

## Notable techniques
- Per-planet timeline simulation with binary-searched `keep_needed`: `simulate_planet_timeline` walks every turn to the horizon resolving "largest vs second-largest" combat, then bisects the minimum garrison that survives all forecast arrivals (cell 0).
- Crash-exploit detection (4-player only): `detect_enemy_crashes` finds two enemy fleets from different owners arriving at the same target within `CRASH_EXPLOIT_ETA_WINDOW=2` turns and queues a follow-up to claim the wreckage one turn after the crash (cell 0).
- Multi-enemy proactive defense via sliding window: `_multi_enemy_proactive_keep` finds the largest temporal stack of inbound enemy fleets within `MULTI_ENEMY_STACK_WINDOW=3` turns and reserves `0.20` of that stacked total (cell 0).
- Three-source swarm with explicit "no two-source subset can solo it" check, gated by `THREE_SOURCE_PLAN_PENALTY=0.98` and `THREE_SOURCE_MIN_TARGET_SHIPS=20` (cell 0).
- Rear-to-front logistics funnel: rear planets (distance > 1.25x front anchor distance) ship 0.68-0.7 of attack budget toward a staging planet closer to the frontier (cell 0).
- Mode-aware `attack_margin_mult`: `is_behind / is_ahead / is_finishing / is_dominating` multiplicatively bias send size and target value (cell 0).
- Path-clearance gap: only sun-collision is checked (`segment_hits_sun`); no per-turn moving-planet path-collision sim. Fleets are aimed straight and assumed to ignore other planets en route.

## Visible evidence
Working `def agent(obs)` at end of cell 0: builds `WorldModel`, returns `plan_moves(world)` or `[]`. Dual-mode `_read(obs, key, default)` for dict/Struct. ~80 named tunables at top of cell. No tests, no plots, no markdown cells — entire notebook is one code cell that writes `submission.py`.

## Relevance to v1.5G
v1.5G already has WorldModel + Hungarian/greedy offense + `find_threats`/`plan_defense` reinforce. Three patterns we don't have:
1. Crash-exploit — opportunistic capture when two rival enemies kamikaze the same planet (synergistic with our path-collision detector).
2. Multi-enemy stacked-arrival defense buffer — keeps ships against temporal stacks of inbound fleets, not just the single largest forecast deficit. Distinct from our `find_threats` walk.
3. Three-source swarm with dominance check ("no two-source subset suffices") gates trio missions cleanly.

Caveat: this agent ranks #672 (score 747.8) — below our v1.4 settling point ~700. Its breadth of mission types is impressive but evidently does not translate to ladder dominance; copying patterns wholesale is unwarranted. The moving-planet path-collision omission is a real bug under our reading of rule E3.

## What could not be determined
- No version history visible inside the cell (comments reference "v6"); whether earlier versions scored higher is unknown.
- No per-mission ablation data; relative contribution of crash-exploit vs reinforce vs swarm is opaque.
- Self-play / sparring records absent — no benchmarks shown in the notebook.
