# Diagnostic summary — heuristic v1.1 Phase 2

**Seeds:** [0, 1, 2, 3, 4]
**Global random.seed:** 42

## Win/loss
Heuristic vs random: **5W-0L** over 5 seeds
- seed 0: heuristic=1, random=-1
- seed 1: heuristic=1, random=-1
- seed 2: heuristic=1, random=-1
- seed 3: heuristic=1, random=-1
- seed 4: heuristic=1, random=-1

## Launch outcomes
- Total launches: **1728**
- Captures: **586**
- Misses: **1142**
- Overall capture rate: **33.9%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 234 | 220 | 14 | 94.0% |
| orbiting | 1324 | 283 | 1041 | 21.4% |
| comet | 170 | 83 | 87 | 48.8% |

## Failure reasons (across all misses)
- `still-neutral-at-arrival`: **417**
- `fleet-destroyed-in-transit`: **389**
- `arrival-after-episode-end`: **236**
- `enemy-defended`: **59**
- `lost-race-to-different-player`: **41**

## Failures by target type x reason
### comet
- `arrival-after-episode-end`: 75
- `still-neutral-at-arrival`: 8
- `fleet-destroyed-in-transit`: 3
- `lost-race-to-different-player`: 1

### orbiting
- `still-neutral-at-arrival`: 399
- `fleet-destroyed-in-transit`: 386
- `arrival-after-episode-end`: 161
- `enemy-defended`: 59
- `lost-race-to-different-player`: 36

### static
- `still-neutral-at-arrival`: 10
- `lost-race-to-different-player`: 4
