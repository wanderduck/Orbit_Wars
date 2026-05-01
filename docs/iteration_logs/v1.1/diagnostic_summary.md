# Diagnostic summary — heuristic v1.1 Phase 2

**Seeds:** [0, 1, 2, 3, 4]
**Global random.seed:** 42

## Win/loss
Heuristic vs random: **0W-5L** over 5 seeds
- seed 0: heuristic=-1, random=1
- seed 1: heuristic=-1, random=1
- seed 2: heuristic=-1, random=1
- seed 3: heuristic=-1, random=1
- seed 4: heuristic=-1, random=1

## Launch outcomes
- Total launches: **2459**
- Captures: **0**
- Misses: **2459**
- Overall capture rate: **0.0%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 1951 | 0 | 1951 | 0.0% |
| orbiting | 459 | 0 | 459 | 0.0% |
| comet | 49 | 0 | 49 | 0.0% |

## Failure reasons (across all misses)
- `still-neutral-at-arrival`: **1275**
- `fleet-destroyed-in-transit`: **837**
- `enemy-defended`: **254**
- `arrival-after-episode-end`: **66**
- `lost-race-to-different-player`: **27**

## Failures by target type x reason
### static
- `still-neutral-at-arrival`: 1019
- `fleet-destroyed-in-transit`: 692
- `enemy-defended`: 195
- `arrival-after-episode-end`: 23
- `lost-race-to-different-player`: 22

### orbiting
- `still-neutral-at-arrival`: 249
- `fleet-destroyed-in-transit`: 143
- `enemy-defended`: 59
- `lost-race-to-different-player`: 5
- `arrival-after-episode-end`: 3

### comet
- `arrival-after-episode-end`: 40
- `still-neutral-at-arrival`: 7
- `fleet-destroyed-in-transit`: 2

---

## Decision (Phase 2 → Phase 3)

**Failure mode is not the one the plan anticipated.**

The plan branched on:
- Path 3.A (orbiting miss → intercept-only) — would be triggered if `>60%` of misses were orbiting/comet.
- Path 3.B (wrong target selection → multi-tier scoring) — would be triggered if `>60%` were on static targets WITH sufficient ships.

What we see:
- 79% of targets ARE static (1951/2459) — superficially matches Path 3.B.
- BUT the failure isn't "wrong target" — it's "**fleet doesn't arrive at target at all**". 51.8% are `still-neutral-at-arrival` (the target stayed neutral while our fleet apparently vanished); 34.0% are `fleet-destroyed-in-transit`. Total 86% of misses share the same root cause.

**Hypothesis:** Per E1/E3 rules, "Collides with any planet (path segment comes within the planet's radius). This triggers combat." Our `safe_angle_and_distance` only checks SUN collision. Fleets in transit to one planet hit OTHER planets along the way and are consumed there — capturing the wrong planet (or being annihilated by its garrison).

Static targets are MORE likely to suffer this because they're typically in the outer ring; fleets fired from one outer-ring planet to another travel the longer arc that's more populated with other planets in the way.

**Proposed Fix #1 (NEW — not in original plan A.1/A.2 list, derived from diagnostic):**

Add **path-clearance check** in `_try_launch`. Before launching at `target`, walk all other planets and find the FIRST planet (by distance along ray) within collision radius of the src→target trajectory. If first-hit is not `target`, skip this target. (Optionally: aim at the first-hit planet instead, since that's where the fleet will actually arrive.)

**Expected impact:** addresses 86% of current launch failures directly. Should jump win-rate from 1/10 baseline to substantially higher.

**Status:** AWAITING USER APPROVAL before implementing this deviation from the original Tier A.1/A.2 fix list.

