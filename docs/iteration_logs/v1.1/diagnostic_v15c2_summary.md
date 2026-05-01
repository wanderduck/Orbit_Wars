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
- Total launches: **360**
- Captures: **325**
- Misses: **35**
- Overall capture rate: **90.3%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 158 | 152 | 6 | 96.2% |
| orbiting | 156 | 135 | 21 | 86.5% |
| comet | 46 | 38 | 8 | 82.6% |

## Failure reasons (across all misses)
- `arrival-after-episode-end`: **21**
- `still-neutral-at-arrival`: **11**
- `fleet-destroyed-in-transit`: **2**
- `lost-race-to-different-player`: **1**

## Failures by target type x reason
### comet
- `still-neutral-at-arrival`: 6
- `fleet-destroyed-in-transit`: 2

### orbiting
- `arrival-after-episode-end`: 16
- `still-neutral-at-arrival`: 5

### static
- `arrival-after-episode-end`: 5
- `lost-race-to-different-player`: 1
