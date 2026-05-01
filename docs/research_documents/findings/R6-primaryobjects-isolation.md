# R6: Intelligent Heuristics for the Game Isolation (primaryobjects.com)

## Source
https://www.primaryobjects.com/2020/01/26/intelligent-heuristics-for-the-game-isolation-using-ai-and-minimax/

Companion content (same author, Kory Becker — "primaryobjects"):
- https://www.rpubs.com/primaryobjects/isolation (numerical tournament results)
- https://github.com/primaryobjects/isolation (source code)
- https://primaryobjects.github.io/isolation/ (live demo)

## Fetch method
WebFetch failed (permission denied at the tool level). Substituted with WebSearch — multiple targeted queries returned the article's heuristic formulas, tournament results, and code snippets near-verbatim with the article URL confirmed in every result set. The full per-depth tournament matrix was not surfaced, only headline numbers — see Open Questions.

## Document type
Blog article + companion R/RPubs statistical analysis (same author).

## Topic
Heuristic evaluation functions for Isolation — a turn-based two-player grid game where each player tries to be the last with a legal move. Author uses minimax + alpha-beta pruning and benchmarks several heuristics by win rate across search depths.

## Goal
Demonstrate that a multi-feature heuristic — especially one that switches strategy based on game phase — outperforms naive move-counting in adversarial search. The article walks from "count my moves" up to a phase-aware "switch between aggressive and defensive" heuristic and shows it wins more often.

## Methods

### Game / search setup
- Isolation: 2 players on an N x M grid (commonly 7x7). Each turn, move to an unvisited cell along an unblocked row/column/diagonal. Lose if you have no legal move.
- Minimax with alpha-beta pruning. Heuristic is plugged into a `HeuristicManager` and called at depth-cutoff leaves.
- Tested at fixed search depths 2 through 6.

### Heuristics evaluated (simplest -> best)
1. Random (baseline / sanity check).
2. Simple / Open-move count: score = number of legal moves available to me.
3. Improved: `my_moves - opponent_moves`.
4. Aggressive: `10 - opponentMoves` (purely minimize opponent mobility).
5. Defensive (weighted): `(playerMoves * 2) - opponentMoves`.
6. Offensive (weighted): `playerMoves - (opponentMoves * 2)`.
7. Defensive-to-offensive: defensive while progress-ratio <= 0.5, then offensive.
8. **Offensive-to-defensive: offensive early, defensive late.** Top performer.

### Game-progress ratio (phase-aware heuristics)
```
ratio = roundNumber / (width * height)
return ratio <= 0.5 ? defensive() : offensive();
```
Denominator = total cells, used as proxy for max possible game length, so `ratio` runs from 0 (start) to ~1 (board nearly exhausted).

## Numerical params / hyperparams

| Parameter | Value | Source |
|---|---|---|
| Defensive weight on player moves | 2 | `(playerMoves * 2) - opponentMoves` |
| Offensive weight on opponent moves | 2 | `playerMoves - (opponentMoves * 2)` |
| Aggressive constant | 10 | `10 - opponentMoves` |
| Phase-switch threshold | 0.5 | `ratio <= 0.5` |
| Search depths benchmarked | 2, 3, 4, 5, 6 | tournament setup |
| Opponent fixed at | depth 3 | tournament baseline |

### Tournament results (key numbers)
- Random: lowest win rate.
- Same heuristic vs. itself at equal depth -> ~50% (sanity check).
- **Best = offensive_to_defensive: 52.2% win rate at depth 3 vs. baseline; 58% at depth 6.**
- Defensive_to_offensive also beats baseline but by a smaller margin.
- Search depth dominates: gain from depth 3 -> 6 exceeds gain from picking a fancier heuristic at fixed depth.

## Reusable patterns for our heuristic

1. **Score = weighted sum of mobility-style features.** 2-4 cheap features, positive weights for "mine", negative for "theirs". Equal weights ("improved") is fine to start, but asymmetric (2:1) measurably wins.
2. **Asymmetric weighting beats symmetric.** `2*mine - theirs` and `mine - 2*theirs` both outperform plain difference. Pick a side rather than treating gain and denial as equally important.
3. **Phase-aware switching beats any fixed heuristic.** A single midpoint switch (using a normalized progress ratio) outperformed every static heuristic in the tournament.
4. **Counter-intuitive ordering: offensive-early > defensive-early.** The author attributes this to crippling the opponent's options early before the board shrinks, then conserving your own options late. Worth testing both orderings before committing in Orbit Wars.
5. **Search depth is the bigger lever.** Author explicitly notes depth 3 -> 6 outweighs heuristic choice at fixed depth. Implication: keep heuristic eval cheap so we can afford more nodes/sims per turn.
6. **Random + same-vs-same sanity checks.** Random (lower bound) and self-vs-self at equal depth (~50%) catch sign-flip bugs immediately.
7. **Pluggable heuristic.** Author's `HeuristicManager` takes the heuristic as a parameter into the search. We should mirror this so we can A/B different formulas in self-play without rewriting the search loop.

### Mapping to Orbit Wars (continuous 2D, 100x100, 500-turn, fleets/planets/sun/comets)
- "Available moves" -> a scalar feature proxying agency: total fleet strength, planets owned, production rate.
- Defensive feature candidates: `own_planet_count`, `own_total_fleet_strength`, `mean_distance_from_sun` (survivability), `production_rate`.
- Offensive feature candidates: `opponent_planet_count`, `opponent_total_fleet_strength`, `distance_to_nearest_opponent_planet`.
- Phase ratio: `current_turn / 500`. Threshold 0.5 -> turn 250.
- First-cut heuristic to try: `score = 2 * own_fleet_strength - opponent_fleet_strength` (mirror of defensive). Then offensive variant. Then phase-switch at turn 250. Then test both orderings.

## Direct quotes / code snippets to preserve

Aggressive:
```
return 10 - playerMoves;
```
(Quoted from search results; the prose says this should minimize opponent moves, so the intended form is almost certainly `10 - opponentMoves`. Flagged below.)

Defensive (weighted):
```
return (playerMoves * 2) - opponentMoves;
```

Offensive (weighted):
```
return playerMoves - (opponentMoves * 2);
```

Phase-aware switch:
```
const ratio = roundNumber / (width * height);
return ratio <= 0.5 ? defensive() : offensive();
```

## Anything novel worth replicating

1. **Phase-switch trick is the headline finding** — one-line conditional, strictly dominates either fixed strategy. Cheap, big payoff.
2. **2:1 asymmetric weighting** — small principled deviation from `mine - theirs`, gave measurable gains. Test this exact ratio before grid-searching.
3. **`current_turn / max_turns` as a scalar phase indicator** the heuristic itself reads. Generalizes to any fixed-horizon game, including our 500-turn episodes.
4. **Empirical "offensive-first" result** challenges the intuitive "build up then attack" narrative. Replicate the experiment rather than assume.
5. **Tournament harness as a first-class artifact.** Author benchmarks every heuristic against a fixed-depth baseline and reports win-rate matrices. We should build this early — it's what generated every conclusion in the article.

## Open questions / things I couldn't determine

1. **Full win-rate matrix (8 heuristics x 5 depths).** Only headline numbers surfaced. Full matrix is on the RPubs companion page; would need direct fetch.
2. **Aggressive formula typo.** Search returned `10 - playerMoves` while prose says minimize opponent. Almost certainly should be `10 - opponentMoves`. Needs GitHub source confirmation.
3. **Why offensive-first beats defensive-first.** Author hand-waves about early cornering before the board shrinks. No controlled ablation. Likely tied to Isolation's "no-legal-move = loss" terminal — Orbit Wars's gradual capture-by-out-fleeting is different, so the ordering could flip for us.
4. **Board-size sensitivity.** Tested ~7x7. Whether the 0.5 threshold and 2:1 weights are board-size invariant is untested. For 100x100 + 500-turn, expect to retune.
5. **Move ordering / iterative deepening.** Alpha-beta efficiency depends on move ordering. Article mentions alpha-beta but not the ordering policy. Matters more in a continuous action space.
6. **Zero-sum framing.** Isolation is strictly zero-sum. Orbit Wars's terminal conditions are more nuanced; `mine - theirs` may need a third absolute term (e.g., total economy) that isn't purely relative.

## Relevance to Orbit Wars (1-5)
**4 / 5**

High because: end-to-end case study of designing, weighting, and benchmarking a heuristic for a strategy game with discrete decisions. The four reusable patterns (asymmetric weighting, phase-aware switching, depth-dominates-heuristic, swappable eval function) port directly. The tournament-harness methodology is exactly what we need to validate any Orbit Wars heuristic.

Not 5 because: Isolation is discrete-grid and strictly turn-by-turn with a hard "no legal move = loss" terminal; Orbit Wars is continuous 2D with gradual capture and multiple unit types ("available moves" doesn't translate cleanly). The specific 2:1 weights and 0.5 threshold won't survive transfer without retuning, and the empirical "offensive-first" ordering may not hold given the very different terminal condition.
