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
- Total launches: **1219**
- Captures: **382**
- Misses: **837**
- Overall capture rate: **31.3%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 162 | 144 | 18 | 88.9% |
| orbiting | 923 | 198 | 725 | 21.5% |
| comet | 134 | 40 | 94 | 29.9% |

## Failure reasons (across all misses)
- `still-neutral-at-arrival`: **512**
- `arrival-after-episode-end`: **226**
- `fleet-destroyed-in-transit`: **87**
- `enemy-defended`: **10**
- `lost-race-to-different-player`: **2**

## Failures by target type x reason
### comet
- `arrival-after-episode-end`: 82
- `still-neutral-at-arrival`: 12

### orbiting
- `still-neutral-at-arrival`: 493
- `arrival-after-episode-end`: 134
- `fleet-destroyed-in-transit`: 87
- `enemy-defended`: 10
- `lost-race-to-different-player`: 1

### static
- `arrival-after-episode-end`: 10
- `still-neutral-at-arrival`: 7
- `lost-race-to-different-player`: 1
