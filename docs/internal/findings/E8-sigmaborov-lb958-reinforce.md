# E8: sigmaborov-lb958-reinforce

## Source
https://www.kaggle.com/code/sigmaborov/lb-958-1-orbit-wars-2026-reinforce

## Fetch method
kaggle kernels pull (succeeded; .ipynb at /tmp/ow_e8/lb-958-1-orbit-wars-2026-reinforce.ipynb, 70 KB). Extracted via Python; analyzed inline.

## Goal
**This notebook is NOT a REINFORCE-algorithm RL agent — it is a heuristic agent of the same lineage as E6 (pilkwang-structured-baseline).** The "REINFORCE" in the slug refers to the **Reinforcement-mission** strategy primitive (a defensive tactic that ships extra garrison to threatened planets), not Williams' policy-gradient algorithm. The slug "lb-958-1" announces a leaderboard score of **958.1**.

This was confirmed by:
- Title from WebFetch attempt: `[LB - 958.1] Orbit Wars 2026 - Reinforce | Kaggle`
- Code header: `# v6: Reinforcement missions ` followed by `REINFORCE_ENABLED = True`, `REINFORCE_MIN_PRODUCTION = 2`, `REINFORCE_VALUE_MULT = 1.35`, etc — strategy-tuning constants, not RL hyperparameters.
- Identical structural fingerprint to E6: same `TOTAL_STEPS = 500`, `HORIZON = 110`, `simulate_planet_timeline`, `WorldModel`, `target_value`, `preferred_send`, `min_ships_to_own_by`, `detect_enemy_crashes`, `aim_with_prediction`, `resolve_arrival_event`. **It is the pilkwang baseline, fork-tuned, with REINFORCE missions added as version v6.**

## Methods
Same 5-layer pipeline as E6 (legal-shot → world-model → defense missions → mission-rank → commit-loop). All physics/world-model/scoring code matches E6 byte-for-byte (or close to it) for the modules sampled. The functional delta vs. E6 is the explicit **Reinforcement Mission**, controlled by these constants:

```python
# v6: Reinforcement missions
REINFORCE_ENABLED = True
REINFORCE_MIN_PRODUCTION = 2          # only reinforce planets with prod ≥ 2
REINFORCE_MAX_TRAVEL_TURNS = 22       # only reinforce if reachable in ≤ 22 turns
REINFORCE_SAFETY_MARGIN = 2
REINFORCE_VALUE_MULT = 1.35           # value multiplier in target_value
REINFORCE_MAX_SOURCE_FRACTION = 0.75  # send at most 75% of source ships
REINFORCE_MIN_FUTURE_TURNS = 40       # only reinforce if ≥ 40 turns remaining
```

The relevant code path (line 1197+ in extracted file):
```python
def build_reinforcement_missions(world, planned_commitments, modes, source_budget_fn):
    if not REINFORCE_ENABLED or not world.threatened_candidates:
        return []
    ...
    for ... in world.threatened_candidates:
        if fall_turn is None or fall_turn > REINFORCE_MAX_TRAVEL_TURNS + 5:
            continue
        ...
        source_cap = min(budget, int(src.ships * REINFORCE_MAX_SOURCE_FRACTION))
        probe_ships = max(PARTIAL_SOURCE_MIN_SHIPS, int(info["deficit_hint"]) + REINFORCE_SAFETY_MARGIN)
        ...
        need = world.reinforcement_needed_for(target_id, turns, planned_commitments)
        send = min(source_cap, need + REINFORCE_SAFETY_MARGIN)
        ...
        value = target_value(target, turns, "reinforce", world, modes)
```

`world.reinforcement_needed_for(planet_id, arrival_turn, planned_commitments)` (line 908) computes the **minimum ships to add at `arrival_turn` such that the planet survives forecasted incoming attacks** — exactly the binary-search-against-projected-state pattern from E6's `min_ships_to_own_by`.

The mission is added to the candidate set BEFORE captures and snipes:

```python
# v6: Reinforcement missions first (competes on score with captures)
reinforce_missions = build_reinforcement_missions(world, ...)
missions.extend(reinforce_missions)
```

So the reinforcement value (×1.35 multiplier) lets it outbid moderate-value captures when a friendly planet is genuinely threatened.

## Numerical params / hyperparams

Same constants as E6 (see E6-pilkwang-structured-baseline.md for the full list). Specific REINFORCE-mission constants reproduced here:

- `REINFORCE_ENABLED = True`
- `REINFORCE_MIN_PRODUCTION = 2`
- `REINFORCE_MAX_TRAVEL_TURNS = 22`
- `REINFORCE_SAFETY_MARGIN = 2`
- `REINFORCE_VALUE_MULT = 1.35`
- `REINFORCE_MAX_SOURCE_FRACTION = 0.75`
- `REINFORCE_MIN_FUTURE_TURNS = 40`
- `REINFORCE_HOLD_LOOKAHEAD = 20` (E9 has this too — implied here from same lineage)
- `REINFORCE_COST_TURN_WEIGHT = 0.35`

Header version comment: `# v6: Reinforcement missions` — strongly suggesting prior versions v1–v5 existed (without reinforcement), and v6 was the breakthrough that pushed leaderboard score to 958.1.

## Reusable code patterns
See E6 report — all of those patterns apply here. The unique addition is `build_reinforcement_missions(...)` and the helper `world.reinforcement_needed_for(...)`. Lift both verbatim into our v1 heuristic when implementing the REINFORCE mission per spec §7.2.5.

## Reported leaderboard score
**958.1** — confirmed via notebook page title `[LB - 958.1] Orbit Wars 2026 - Reinforce | Kaggle`. The slug `lb-958-1-orbit-wars-2026-reinforce` parses as "LB 958.1, Orbit Wars 2026, Reinforce[ment-mission]".

This is the SECOND-highest known leaderboard score among the reference notebooks (E9 = 1224 is higher). Both are heuristic.

## Anything novel worth replicating

Beyond what E6 already covers:

1. **The REINFORCE-mission pipeline is the differentiator vs the no-defensive-coordination baseline.** Adding pre-emptive defense missions that compete with offense on score (with 1.35× value multiplier) is what pushed this fork to LB 958.1.
2. **`world.reinforcement_needed_for(planet_id, arrival_turn, planned_commitments)`** — symmetric to `min_ships_to_own_by` but solving "minimum ships needed AT `arrival_turn` to survive". Adopt verbatim.
3. **Mission ordering: reinforcement first, then captures/snipes/swarm/etc.** — the score-multiplier ensures reinforce wins ties when genuinely needed but doesn't dominate when not. Cleaner than gating defense as a separate phase.
4. **`REINFORCE_MAX_SOURCE_FRACTION = 0.75`** — never ship more than 75% of a source planet's garrison for defense. Prevents over-stripping a producer to defend a marginal target.
5. **`REINFORCE_MIN_FUTURE_TURNS = 40`** — don't reinforce if game is nearly over; ship-count optimization takes over instead.

## Direct quotes / code snippets to preserve

```python
# Constants (from header)
REINFORCE_ENABLED = True
REINFORCE_MIN_PRODUCTION = 2
REINFORCE_MAX_TRAVEL_TURNS = 22
REINFORCE_SAFETY_MARGIN = 2
REINFORCE_VALUE_MULT = 1.35
REINFORCE_MAX_SOURCE_FRACTION = 0.75
REINFORCE_MIN_FUTURE_TURNS = 40

# Mission scoring (from value path)
elif mission == "reinforce":
    value *= REINFORCE_VALUE_MULT
```

## Open questions / things I couldn't determine

- **Exact diff vs E6 (pilkwang)**: are E8 and E6 identical except for tuning, or is E8 missing some E6 features (e.g., crash-exploit)? Given E8's "v6: Reinforcement missions" header, E8 is likely the predecessor to pilkwang's v11 — a sigmaborov fork that added reinforce missions but possibly without the later additions. Need a diff to confirm.
- **Whether the LB 958.1 score is from a 2-player or 4-player ladder** — Kaggle ranking aggregates both; not separable from the title alone.
- **Date of LB 958.1 measurement** — leaderboard moves; the score is a snapshot.
- **The full mission-set this version supports** — does it have crash_exploit, swarm, snipe? Constants suggest yes, but confirmation requires reading more cells.
- **Author's commentary** — markdown cells (~5-10 in front matter) likely explain WHY the changes; not extracted in detail.
