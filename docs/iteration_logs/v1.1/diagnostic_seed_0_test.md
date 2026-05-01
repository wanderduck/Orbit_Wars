# Diagnostic summary — heuristic v1.1 Phase 2

**Seeds:** [0]
**Global random.seed:** 42

## Win/loss
Heuristic vs random: **1W-0L** over 1 seeds
- seed 0: heuristic=1, random=-1

## Launch outcomes
- Total launches: **181**
- Captures: **70**
- Misses: **111**
- Overall capture rate: **38.7%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 34 | 33 | 1 | 97.1% |
| orbiting | 130 | 36 | 94 | 27.7% |
| comet | 17 | 1 | 16 | 5.9% |

## Failure reasons (across all misses)
- `still-neutral-at-arrival`: **65**
- `fleet-destroyed-in-transit`: **21**
- `arrival-after-episode-end`: **16**
- `lost-race-to-different-player`: **7**
- `enemy-defended`: **2**

## Failures by target type x reason
### orbiting
- `still-neutral-at-arrival`: 55
- `fleet-destroyed-in-transit`: 21
- `arrival-after-episode-end`: 9
- `lost-race-to-different-player`: 7
- `enemy-defended`: 2

### static
- `still-neutral-at-arrival`: 1

### comet
- `still-neutral-at-arrival`: 9
- `arrival-after-episode-end`: 7
