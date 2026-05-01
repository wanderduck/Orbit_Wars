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
- Total launches: **436**
- Captures: **320**
- Misses: **116**
- Overall capture rate: **73.4%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 198 | 138 | 60 | 69.7% |
| orbiting | 220 | 165 | 55 | 75.0% |
| comet | 18 | 17 | 1 | 94.4% |

## Failure reasons (across all misses)
- `arrival-after-episode-end`: **101**
- `still-neutral-at-arrival`: **13**
- `lost-race-to-different-player`: **1**
- `fleet-destroyed-in-transit`: **1**

## Failures by target type x reason
### static
- `arrival-after-episode-end`: 57
- `still-neutral-at-arrival`: 3

### comet
- `still-neutral-at-arrival`: 1

### orbiting
- `arrival-after-episode-end`: 44
- `still-neutral-at-arrival`: 9
- `lost-race-to-different-player`: 1
- `fleet-destroyed-in-transit`: 1
