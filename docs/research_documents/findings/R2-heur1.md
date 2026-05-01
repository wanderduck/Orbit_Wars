# R2: heur1.pdf

## Source
/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/research_documents/heur1.pdf

## Document type
Peer-reviewed journal article (Journal of Intelligent Learning Systems and Applications, 2019, 11, 15-31). Short empirical paper / undergraduate-style research note. ~17 pages including references. Published by Scientific Research Publishing under CC BY 4.0 (p. 15). DOI: 10.4236/jilsa.2019.112002.

## Title and authors (if known)
"Research on Different Heuristics for Minimax Algorithm Insight from Connect-4 Game" — Xiyu Kang (Beijing Univ. of Technology), Yiqi Wang (Dalian Polytechnic Univ.), Yanrui Hu (Penn State). Co-first authors. Received 2019-01-20, accepted 2019-03-04, published 2019-03-07 (p. 15).

## Goal
The paper compares two hand-crafted heuristic evaluation functions for a Minimax + alpha-beta Connect-4 player, and empirically studies how (a) search depth and (b) the number of features in the heuristic affect playing strength, decision time, and node count (pp. 15-17). It is explicitly framed as a complement to the algorithmic / knowledge-based Connect-4 literature: rather than proving a winning strategy, it asks "which evaluation function is better, and how do depth and feature-count interact" (p. 17). Connect-4 was solved by Allis (1988) and Allen (independently) — the authors note this and instead focus on heuristic design choices (pp. 16-17).

## Methods
- Classical depth-limited Minimax with alpha-beta pruning. Pseudocode shown verbatim on p. 18 (Figure 1) and a flowchart on p. 20 (Figure 3). Standard MAX/MIN recursion, with HV initialised to -inf for MAX nodes and +inf for MIN nodes (pp. 19-20).
- Two heuristic functions are designed and pitted against each other:
  - **Heuristics-1 (H1, "feature-based")**: scans the board for 4 named features (Win / Three-in-a-row / Two-in-a-row / Single piece), each with sub-cases tied to whether the squares immediately extending the line are *playable* (i.e. either filled below or at the very bottom). H1 returns the signed sum of detected feature values; positive for the player, negative for the opponent (pp. 21-25, esp. Tables 1 and 2 on p. 22; flowchart Figure 11 on p. 26).
  - **Heuristics-2 (H2, "positional")**: ignores feature/line semantics entirely. It assigns each of the 42 squares a static "expansion-space" weight and sums weights over a player's pieces. Centre rows/columns get higher weights, corners get lower (matrix on p. 25).
- Three experiments (Table 5, p. 27) controlling four variables (Table 4, p. 27): depth, "random move" frequency (one random pick from the top-2 columns every 3 moves), feature subset, and which heuristic. Three indices measured (Table 3, p. 27): time to decide, number of nodes expanded, winning percentage.
- A "random move every 3rd move" perturbation (Table 4, p. 27) is used to inject diversity so the same depth pair does not produce a deterministic, repeated game.
- Implementation: Visual Studio 2015 (p. 26).

## Numerical params / hyperparams
- **Board / game**: 7 columns x 6 rows = 42 squares. Win condition: 4 in a row. Gravity: piece falls to lowest unoccupied square.
- **Search depths tested**: 2, 4, 6, 8 (Table 5).
- **Rounds per match-up**: 100 rounds for situations 1 and 3; Table 6 caption says "10 rounds" (inconsistency).
- **Random-move policy**: at every 3rd move, pick uniformly from top-2 candidate columns.
- **Heuristic-1 feature values (Table 2, p. 22)**:
  - Feature 1 (4-in-a-row, win): **Infinity**
  - Feature 2 (three connected): **Infinity** (both adjacent playable) | **900,000** (one adjacent / gap-2 pattern) | **50,000** (no forcing future)
  - Feature 3 (two connected): **40,000 / 30,000 / 20,000 / 10,000** depending on open-square count along the line
  - Feature 4 (single piece, by column): **200 / 120 / 70 / 40** for column d / c-e / b-f / a-g
- **Heuristics-2 positional matrix** (p. 25):
  ```
  3  4  5  7  5  4  3
  4  6  8  10 8  6  4
  5  8  11 13 11 8  5
  5  8  11 13 11 8  5
  4  6  8  10 8  6  4
  3  4  5  7  5  4  3
  ```
- **Reported win rates**:
  - Single-feature win rates of H1 over H2 at depth 4 (Table 7, p. 28): F1=0.48, F2=0.40, F3=0.48, F4=0.40.
  - Combined-feature win rates (Table 8, p. 28): F1+F2=0.54, F1+F2+F3=0.60, all four features=0.80.
  - H1 vs H2 at matched depth (Table 9, p. 28): depth 2 -> H1 0.24 / H2 0.76; depth 4 -> 0.60 / 0.39; depth 6 -> 0.76 / 0.22; depth 8 -> 0.81 / 0.19.

## Reusable patterns for our heuristic

- **Hierarchical, multiplicatively-separated value tiers.** H1 uses values that span ~7 orders of magnitude: terminal win = Infinity, near-forced win = 9e5, mild advantage = 5e4 / 4e4, opening positional bonus = 200 / 120 / 70 / 40 (Table 2, p. 22). The gap is intentional so a higher tier always dominates lower tiers in summation. For Orbit Wars: terminal (capture-decisive) >> near-decisive >> tempo / positioning >> trickle bonuses. Use multiplicative separation, not additive nudges.
- **Reachability, not just adjacency.** H1 distinguishes "three connected" cases by whether the next square is actually playable (p. 23). Mapping: when scoring a target planet, do not score by raw distance — score by whether our fleet can physically arrive before (a) the target rotates into the sun's path, (b) an enemy fleet reaches it first, (c) the planet's garrison out-grows our fleet given growth-during-flight.
- **Penetration depth as a feature.** Feature 3 value scales with the number of *open* squares extending the line. Analogue: when evaluating a forward axis, score should grow with how many *additional* targets the same trajectory threatens.
- **Centre-bias / anti-centre positional matrix.** H2 (p. 25) is a static board-square value matrix peaking at the centre. For Orbit Wars: invert sign for fleet-trajectory scoring (the sun makes the centre a hazard zone).
- **Two-heuristic ablation as debugging.** Let H1 and H2 fight each other (Table 9, p. 28). Keep at least two materially different heuristic agents in-tree and run round-robin matches as a regression test.
- **Feature ablation drives feature ranking.** Tables 7-8 show that adding features monotonically helps but the marginal gain is large only for some. Implement target-scoring as a sum of named, individually-toggleable terms; run leave-one-out tournaments to rank them; delete features that hurt or do nothing.
- **Depth substitutes for cleverness — up to a point.** Table 9 shows H1 at depth 8 beating H2 at depth 8 with 0.81 winrate, but the per-move time at depth 6 is already ~40 s. For us with `actTimeout=1`s, this implies: invest in cheap forward-rollout (1-2 turn lookahead) before subtle features.
- **Random-move perturbation as exploration.** "Random move = 3" breaks deterministic tournament loops. Useful for both anti-dithering and training-data diversity.
- **Online 1% tuning hook** (proposed, p. 29). Adjust heuristic values by +/-1% after a loss — primitive policy-gradient that's cheap to implement.
- **Alpha-beta carries to our setting only for short rollouts.** A 1-2-step expectimax over our top-N candidate actions with opponents modelled as their own greedy heuristic is a defensible analogue.

## Direct quotes / code snippets to preserve

Minimax pseudocode (p. 18, Figure 1):
```
function minimax(node, depth, maximizingPlayer) is
    if depth = 0 or node is a terminal node then
        return the heuristic value of node
    if maximizingPlayer then
        value := -inf
        for each child of node do
            value := max(value, minimax(child, depth - 1, FALSE))
        return value
    else (* minimizing player *)
        value := +inf
        for each child of node do
            value := min(value, minimax(child, depth - 1, TRUE))
        return value
```

> "Heuristic functions determine which branch to follow by sorting the alternatives in each branch-step based on available information." (p. 17)
> "If we increase the search depth of a relatively weaker heuristic with much less number of features, that 'weaker' heuristic can beat its opponent with more features." (p. 29)
> "If one of the heuristics loses the game, we can adjust its heuristic value by 1% higher or lower to make it sounder." (p. 29)

## Anything novel worth replicating
1. **Heuristic feature-tier separation by orders of magnitude** (Table 2, p. 22). Easiest 1-day win: rewrite our target-scoring as `score = INF*term_terminal + 1e6*term_decisive + 1e3*term_advantage + term_positional` and stop normalising things to [0,1].
2. **Reachability-aware feature accounting** (pp. 22-24). Replace any "Manhattan distance to target" term with "earliest arrival time given fleet-speed-vs-size and rotation prediction."
3. **Two-heuristic ablation tournament** as a regression harness. Build before committing to a strategy.
4. **Penetration-depth feature** (Feature 3). Reward paths that threaten multiple targets.
5. **Random-move epsilon for exploration**. Cheap, breaks deadlocks.
6. **Static positional matrix**. Useful as a precomputed sun-penalty / centre-of-mass map even if the sign is flipped relative to Connect-4.
7. **Online 1% tuning loop**. Quick coarse calibration without ML infrastructure.

## Open questions / things I couldn't determine
- Table 6 caption ("10 rounds") vs Table 5 situation 1 ("100 rounds") inconsistency.
- "Infinity" sentinel implementation — should be 1e12 not float-inf to keep arithmetic safe.
- Tables 8 and 9 win-rate inconsistency at depth 4 (0.80 vs 0.60) — same experiment with different sample sizes? Paper doesn't explain.
- No overfitting checks: H1's coefficients (200, 120, 70, 40, etc.) stated by fiat with no described tuning protocol.
- Paper does not address simultaneous-move or multi-player games at all.

## Relevance to Orbit Wars (1-5)
**2.** The paper's *concrete* contributions (Connect-4 win-detection feature set, 7x6 positional matrix, alpha-beta pruning) do not transfer — Orbit Wars is real-time, simultaneous-move, 4-player, continuous-2D, with stochastic comets and a moving sun. However, the *meta-level patterns* (multi-tier value separation, reachability-aware features, feature-ablation tournaments, depth-vs-features trade-off, random-move exploration) are directly applicable to how we structure `src/orbit_wars/heuristic/` and our self-play evaluation harness. Treat this paper as scaffolding for *how to think about* a heuristic, not as a source of equations.
