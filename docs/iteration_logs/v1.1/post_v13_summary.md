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
- Total launches: **347**
- Captures: **258**
- Misses: **89**
- Overall capture rate: **74.4%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 150 | 116 | 34 | 77.3% |
| orbiting | 147 | 125 | 22 | 85.0% |
| comet | 50 | 17 | 33 | 34.0% |

## Failure reasons (across all misses)
- `arrival-after-episode-end`: **75**
- `still-neutral-at-arrival`: **14**

## Failures by target type x reason
### static
- `arrival-after-episode-end`: 31
- `still-neutral-at-arrival`: 3

### comet
- `arrival-after-episode-end`: 31
- `still-neutral-at-arrival`: 2

### orbiting
- `arrival-after-episode-end`: 13
- `still-neutral-at-arrival`: 9
