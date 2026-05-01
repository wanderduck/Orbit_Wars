# R5: Comprehensive Research Report on Heuristic Algorithms and Design Frameworks

## Source
docs/research_documents/Comprehensive Research Report on Heuristic Algorithms and Design Frameworks for Tracking Mechanics, Players, and Objectives in Interactive Environments.md

## Document type
Markdown research compilation (synthesis essay with academic citations, ~200 lines, embedded equation images and 39 footnoted sources). Style is expository/survey rather than technical reference; few concrete formulas, almost no code.

## Topic
A two-paradigm survey of heuristics in interactive systems: (1) computational heuristics for spatial pathfinding, adversarial state-search, and General Game Playing (GGP), and (2) cognitive/usability heuristics (HEP, Nielsen, MDA) for tracking mechanics, players, and objectives. Branches outward into sports telemetry, biometrics, and engagement analytics (lines 1-158).

## Goal
To frame "tracking mechanics, players, and objectives" as a unified problem joining algorithmic search (A*, MCTS, Alpha-Beta) with player-experience design (HEP, Nielsen, juice). The document presents itself as a "comprehensive analysis" intended to inform development teams designing such tracking systems (lines 7, 148-152). It is not a tutorial — it is more like a graduate-survey-style essay with deployment-ready prompt-engineering framing as its terminal artifact.

## Methods
Algorithms, frameworks, and techniques explicitly discussed:

**Pathfinding and informed search** (lines 13-40):
- A* search with evaluation `f(n) = g(n) + h(n)` (lines 15-22).
- Dijkstra's Algorithm — A* with `h(n) = 0`, omnidirectional, optimal but expensive (lines 20, 36).
- Greedy Best-First Search — A* with `h(n)` heavily overestimating; expands purely toward perceived goal; vulnerable to local optima (lines 23-24, 38).
- Admissibility (`h <= true cost`) and monotonicity for guaranteed optimality (line 22).
- Distance Oracle — precomputed all-pairs shortest path lengths (lines 27-28).
- Path Database — gradient form of Distance Oracle storing only the next optimal step (line 28).
- D*-Lite (Dynamic A*) and Lifelong Planning A* (LPA*) — incremental rehoming for mutable maps (lines 30, 39).
- Hierarchical Pathfinding A* (HPA*) (line 32).
- Jump Point Search (JPS) — symmetric pruning for uniform grids (lines 32, 40).

**Adversarial state-search** (lines 46-52):
- Minimax + Alpha-Beta Pruning operating on `heuristic(board)` returning integer evaluations (lines 48-50).
- Meta-heuristics: e.g., the "broadside" in Hex (perpendicular construction) (line 52).
- "If in doubt, capture" hard-coded behavioral heuristic for capture games (line 52).

**General Game Playing / GVGAI** (lines 54-62):
- Monte Carlo Tree Search (MCTS) over unknown rules (line 58).
- Rolling Horizon Evolutionary Algorithm (RHEA) (line 58).
- Heuristic fitness components: avatar info, Euclidean distance to nearest functional sprite, and *loss-avoidance prioritized over point acquisition* (line 58).
- Markov models + state aggregation collapsing mechanically similar states into single nodes (lines 60-62).
- Hybrid model selecting between probabilistic tracking and player-heuristic search by data sparsity (line 62).

**Multi-agent / network** (lines 64-66):
- Selfish-routing analogy (Tragedy of the Commons / Prisoner's Dilemma) — local heuristic optimization causes global sub-optimization in multi-agent shared spaces (lines 64-66).

**Usability frameworks** (lines 70-94):
- Heuristics for Evaluating Playability (HEP) — Game Play, Game Usability, Game Mechanics, Game Story (lines 72-78).
- Nielsen's 10 heuristics: Visibility of System Status (lines 82-86), Match Between System and Real World (lines 86-87).
- Intentional obfuscation as a design heuristic (lines 88-94): asymmetric information (Fury of Dracula), forced memory load (Stratego, Bridge).

**Aesthetic/feedback frameworks** (lines 98-108):
- MDA (Mechanics → Dynamics → Aesthetics) and DMC Pyramid (Dynamics, Mechanics, Components) (lines 100-104).
- "Juice" — hyper-responsive sensory feedback; non-linear acceleration curves for movement (lines 106-108).

**Predictive/empirical methods** (lines 116-128):
- Neural networks on NFL tracking, F1 ~ 0.40 baseline (line 116).
- K-means clustering on 3M+ NBA SportVU trajectory images for attack-pattern discovery (line 118).
- LSTM and GRU on multi-object soccer trajectories (line 120).

**Telemetry / engagement** (lines 134-144):
- Event-based cohort retention (GameAnalytics, SonaMine) — track retention conditional on a specific in-game event (e.g., purchasing "SniperRifle") (lines 134-138).
- Stickiness ratio = DAU / MAU (line 138).
- Biometric: ERP eye-tracking (fixations, saccades, smooth pursuits); caveat that gaze != attention (line 142).
- Dynamic match-outcome interventions (bot insertion to prevent loss streaks) (line 144).

## Numerical params / hyperparams
The document is light on numbers. The concrete numerical statements are:

- A* evaluation function: `f(n) = g(n) + h(n)` (line 17, image-rendered).
- Admissibility condition: `h(n) <= h*(n)` (line 22).
- Dijkstra equivalence: `h(n) = 0` (line 20).
- Greedy Best-First when `h(n) >> g(n)` (line 23).
- NFL play-success neural-network baseline: F1 ~ 40% (line 116).
- NBA SportVU dataset scale: "over 3 million trajectory images" processed via K-means (line 118).
- Fitness-tracker abandonment: "up to 50% of users abandon... within 6 to 12 months" (line 126) — irrelevant to Orbit Wars.
- HEP categories: 4 (Game Play, Game Usability, Game Mechanics, Game Story) (line 74).
- Nielsen heuristics: 10 (line 82).

No tunable agent hyperparameters (epsilon, gamma, MCTS exploration constant, depth limits, etc.) are provided. The document references named algorithms without their parameter conventions.

## Reusable patterns for our heuristic
Filtered against the Orbit Wars constraints in `CLAUDE.md` (1s actTimeout, stateless `agent(obs)`, 100x100 board with sun + comets + orbiting planets, log-scaled fleet speed, "largest vs second-largest" combat). Only the directly applicable patterns are listed; usability/MDA/biometrics are non-reusable for an evaluation-only agent.

1. **A* `f = g + h` decomposition for target-priority scoring** (line 17). Use the same shape for each candidate `(source_planet, target_planet)` pair: `score(target) = travel_cost(source, target) + h(target)`, where `h` blends estimated capture cost (defender garrison + intercept risk) and strategic value. This is exactly how the document recommends balancing "known cost" and "estimated remaining cost" (lines 16-22). For Orbit Wars, `g` is the actual travel time given the log-scaled fleet speed; `h` should encode value of the target minus expected losses.

2. **Admissibility discipline** (line 22). When designing the target-priority heuristic, never *underestimate* the strategic value of a target relative to others — but for travel-time estimation, *underestimating* (admissible) is the safe direction. Practical translation: prefer optimistic ETA estimates so the agent doesn't spuriously abandon viable captures, and prefer conservative threat estimates so it doesn't lunge into bad fights.

3. **Greedy Best-First failure mode is a direct warning to our current agent** (lines 23-24, 38). The "nearest-planet sniper" baseline noted in `CLAUDE.md` is precisely Greedy Best-First: it expands by `h` only and ignores `g`. The document calls out this pattern's "susceptibility to local optima" and "blind reliance even when the heuristic is structurally flawed." A first improvement is to add a true `g(n)` term — actual travel cost (turns + ships lost in transit to sun/comets) — to dethrone the nearest-target bias.

4. **Distance Oracle / Path Database** (lines 27-28). Orbit Wars has up to ~50-200 planet locations with deterministic rotation. A turn-0 precompute of pairwise shortest-arrival-times for representative fleet sizes — keyed by `(source_id, target_id, future_turn)` and stored in module-level cache — perfectly fits the "Path Database" pattern of caching only the next-step decision rather than full trajectories. Memoize per-episode; reset on new episode (key by `obs.player` plus a step-zero fingerprint).

5. **Dynamic rehoming (D*-Lite / LPA*)** (lines 30, 39). Comets can appear/disappear and planets rotate, so the topology mutates each turn. The conceptual takeaway is to *recycle* prior search trees, not recompute from scratch each turn. In practice for a 1s budget with ≤ ~50 real planets this is overkill; a full re-evaluation is cheap. Note it as a fallback if compute pressure rises.

6. **Loss-avoidance prioritized over point gain** (line 58). The GVGAI MCTS heuristic literature explicitly weights *not losing* over *winning faster*. In Orbit Wars (out-fleeting capture, sun annihilation, comet collisions), a heuristic that asymmetrically penalizes fleet annihilation more than it rewards equivalent captures matches this principle. Concretely: weight `expected_loss * λ` with `λ > 1` against `expected_gain` in scoring.

7. **"If in doubt, capture"** (line 52). Hard-coded fallback rule from connection-game heuristics: when no clearly best move exists, send `garrison + 1` to the cheapest unowned target. Keep the current baseline behavior as the default branch when the scored search is inconclusive — but only after the `g + h` decomposition is in place.

8. **State aggregation** (lines 60-62). Cluster mechanically equivalent planet configurations (e.g., "all enemy-owned outer-orbit planets within 15 turns of my nearest fleet") into single decision categories. Reduces effective branching for any lookahead. For our 4-player game, aggregating "all opponents" into a single threat profile is a pragmatic first cut.

9. **Multi-agent / selfish-routing warning** (lines 64-66). In a 4-player game where everyone runs a similar greedy heuristic, mass-converging on the same high-value target is the Tragedy-of-the-Commons failure mode. Mitigation: penalize targets that we predict opponents are also racing toward (proximity-weighted opponent fleet vector). Even a crude `competitor_pressure(target)` term changes outcomes.

10. **Asymmetric information / hidden state** (lines 88-94). Not a heuristic for *us*, but a reminder that hidden information in the obs (e.g., comet trajectories not telegraphed beyond what the schema exposes) should be treated as adversarially unknown rather than statistically ignorable.

11. **Meta-heuristics from connection games** (lines 50-52). The "broadside" pattern (build perpendicular to your goal direction) translates to: don't queue all fleets along a single attack vector; spread captures so a single sun-trajectory or comet path cannot wipe a wave. Useful for fleet-routing diversification.

## Direct quotes / code snippets to preserve

(line 17, equation): f(n) = g(n) + h(n)

(line 22): "If h(n) is strictly less than or equal to the actual cost to reach the goal, the heuristic is deemed 'admissible,' guaranteeing that the algorithm will find the optimal path without overestimating the required effort... When h(n) perfectly matches the exact cost to the objective, the algorithm operates flawlessly, tracking the absolute best path and never expanding unnecessary collateral nodes."

(line 23-24): "if the heuristic function dramatically overestimates the cost... the algorithm transforms into Greedy Best-First Search... The primary vulnerability is its susceptibility to local optima; it will eagerly pursue a node at the end of an exceptionally long or blocked path merely because the absolute heuristic coordinates appear close to the objective, relying blindly on the heuristic even when it is structurally flawed."

(line 28): "The Path Database functions as a gradient of the Distance Oracle, storing only the immediate next step required in an optimal path rather than the entire route, thereby drastically reducing the memory overhead required to track player objectives."

(line 30): "These algorithms facilitate continual 'rehoming,' allowing the tracking agent to adjust its search agenda dynamically as the environment mutates, continually recycling previous search trees rather than recalculating paths from scratch when obstacles appear."

(line 52): "In games featuring capturing mechanics, a universally hard-coded behavioral heuristic frequently implemented is 'if in doubt, capture'—a reflection of deeply rooted human behavioral patterns when interacting with zero-sum tracking mechanics."

(line 58): "The core parameters used to establish these heuristic fitness functions track localized, observable phenomena: avatar-related information provided directly by the engine, spatial exploration encouraged via Euclidean distance calculations to the nearest functional sprites, and a punitive tracking approach that heavily prioritizes loss avoidance over immediate point acquisition."

(line 62): "By aggregating varied but mechanically similar states into singular nodes, the algorithm dynamically selects between probabilistic tracking and player heuristic search based on the sparsity of available observed data."

(line 66, multi-agent): "When multiple independent agents act selfishly—optimizing their own tracking heuristic to minimize internal network cost while offloading the traversal burden onto external, farther peering points—it results in global sub-optimization analogous to the Tragedy of the Commons."

No code snippets exist in the document — it references `heuristic(board)` only in prose (line 50) and renders all formulas as base64-embedded images (lines 17, 200-212).

## Anything novel worth replicating
- **Loss-avoidance asymmetry as a default scoring weight** (line 58). Not novel in RL literature, but cleanly stated and directly applicable as a multiplier `λ > 1` on the fleet-loss term in our score function. Sun-collision and comet-collision risk should drive λ higher than a typical RTS.
- **Path Database as a first-step lookup**, not a full trajectory cache (line 28). For 1-second turn budgets, caching only the next move per `(source, target, current_turn)` triple is the right ergonomic — and matches the "stateless function with module cache" pattern Orbit Wars submission requires.
- **Selfish-routing collisions as an explicit scoring term** (lines 64-66). The framing of multi-agent greedy heuristics as Tragedy of the Commons is unusual in agent-design writeups and worth borrowing for the 4-player target-contention term.
- **State aggregation as a sparsity-driven switch** (line 62) — when little is known about a configuration class, default to probabilistic; when much is known, default to learned heuristic. For our setting, this means: pretty heuristic for early-turn planet capture (well-explored), random/probabilistic for sun-grazing or comet-intercept (rarely simulated).

## Open questions / things I couldn't determine
- **No concrete values for λ (loss aversion weight), MCTS exploration constants, RHEA generation/population sizes, or A* node-expansion limits.** The document discusses these algorithms qualitatively only.
- **No discussion of time-budgeted anytime variants of A*** (relevant since we have 1s/turn). D*-Lite is named (line 30) but not parameterized.
- **No treatment of partially observable / multi-agent search**, despite mentioning multi-agent dynamics (lines 64-66). The "selfish routing" insight is qualitative; no operational formula is given.
- **No formula for a heuristic evaluation function**. The line `heuristic(board)` (line 50) is treated as a black-box; the document never illustrates how to construct one for a specific game.
- **Section "Generative Evaluation Frameworks for Algorithmic Heuristics"** (lines 146-152) promises a "deployment-ready" generative prompt but never provides the prompt itself — appears truncated or self-referential, possibly intentional padding.
- **No quantitative benchmarks** comparing the listed algorithms (e.g., A* vs JPS vs HPA* on grid sizes comparable to 100x100). Cited papers (footnotes 2, 4, 7) likely contain these, but they are not summarized here.

## Relevance to Orbit Wars (1-5)
**3 / 5.**

Justification: The pathfinding section (A*, admissibility, Greedy Best-First failure mode, Path Database, dynamic rehoming) and the adversarial-search section (loss-avoidance weighting, "if in doubt, capture", state aggregation, selfish-routing collisions) are directly transferable to `src/orbit_wars/heuristic/`. The document explicitly diagnoses the failure mode of our current "nearest-planet sniper" baseline (lines 23-24) and supplies the right conceptual fix (`g + h` decomposition with admissible `h`). However:

- The document is a *survey* — every concept is at the level of "named algorithm + one paragraph"; no implementation guidance, no parameter recommendations, no code.
- ~50% of the content (HEP, MDA, juice, Nielsen heuristics, biometrics, engagement telemetry, fitness trackers) is irrelevant to a stateless agent function — these address human-facing UI, not algorithmic decision-making.
- The most useful single takeaway (`f = g + h` with admissibility) is well-known and can be sourced from any AI textbook with more rigor.

Net: useful as a *checklist of patterns to consider* and a clear articulation of why our current agent is structurally weak, but not load-bearing as a primary reference. Treat as a confirmation-and-orientation document; pair it with a focused source on game-tree search or MCTS for the actual algorithmic backbone.
