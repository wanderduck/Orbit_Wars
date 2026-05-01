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
- Total launches: **1271**
- Captures: **474**
- Misses: **797**
- Overall capture rate: **37.3%**

## By target type
| Type | Total | Captures | Misses | Capture rate |
|------|------:|---------:|-------:|-------------:|
| static | 166 | 150 | 16 | 90.4% |
| orbiting | 836 | 250 | 586 | 29.9% |
| comet | 269 | 74 | 195 | 27.5% |

## Failure reasons (across all misses)
- `still-neutral-at-arrival`: **365**
- `arrival-after-episode-end`: **209**
- `fleet-destroyed-in-transit`: **143**
- `enemy-defended`: **44**
- `lost-race-to-different-player`: **36**

## Failures by target type x reason
### orbiting
- `still-neutral-at-arrival`: 289
- `fleet-destroyed-in-transit`: 143
- `arrival-after-episode-end`: 76
- `enemy-defended`: 44
- `lost-race-to-different-player`: 34

### static
- `arrival-after-episode-end`: 8
- `still-neutral-at-arrival`: 6
- `lost-race-to-different-player`: 2

### comet
- `arrival-after-episode-end`: 125
- `still-neutral-at-arrival`: 70
