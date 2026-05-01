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
- Total launches: **381**
- Captures: **347**
- Misses: **34**
- Overall capture rate: **91.1%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 191 | 177 | 14 | 92.7% |
| orbiting | 162 | 152 | 10 | 93.8% |
| comet | 28 | 18 | 10 | 64.3% |

## Failure reasons (across all misses)
- `still-neutral-at-arrival`: **18**
- `arrival-after-episode-end`: **16**

## Failures by target type x reason
### comet
- `still-neutral-at-arrival`: 10

### orbiting
- `arrival-after-episode-end`: 7
- `still-neutral-at-arrival`: 3

### static
- `arrival-after-episode-end`: 9
- `still-neutral-at-arrival`: 5
