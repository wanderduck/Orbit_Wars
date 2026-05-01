# R1: heur0.pdf

## Source
/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/research_documents/heur0.pdf

## Document type
Short survey / review article (10 pages, ~9 pages of body + references). Published in a Dean&Francis venue, ISSN 2959-6157. Reads as an undergraduate-level literature review of grid-based heuristic pathfinding for video games. Light on math; heavy on prose summary of well-known algorithms. Contains no novel algorithm, no benchmark code, no new empirical results — the only "data" figure (Fig. 3) is a generic LPA*-vs-D*Lite millisecond chart with no methodology section.

## Title and authors (if known)
- Title: "Heuristic Pathfinding Algorithms in Video Games Indepth Analysis and Performance" (p. 1)
- Author: Runjie Lu, Department of Art and Science, Santa Clara University, lurunjie1301@gmail.com (p. 1)
- Year: not explicitly stated on the title page; references span 2015-2024 so it post-dates 2024 (ref [16] is dated 2024, p. 9).
- Keywords: "Heuristic Pathfinding, Hierarchical Pathfinding, Dijkstra's Algorithm, Jump Point Search (JPS), Bidirectional Search" (p. 1).

## Goal
The paper is a non-technical narrative survey of heuristic pathfinding techniques used by NPC navigation in commercial video games. It walks through Dijkstra -> A* -> Hierarchical Pathfinding -> JPS -> Bidirectional Search -> D*-Lite/LPA* -> Flow Fields -> ML/RL approaches, with case studies (StarCraft II, Zelda: Breath of the Wild, Red Dead Redemption 2). The stated thesis is that "the balance between computational efficiency and path optimality" is the central design trade-off (abstract, p. 1).

## Methods
No experimental methodology. The article describes (verbally) the following algorithms (pages noted):
- **Dijkstra's algorithm** — single-source shortest path; expands all unvisited neighbors with minimal distance from start (p. 1).
- **A\*** — augments Dijkstra with admissible heuristic h(n); minimizes f(n) = g(n) + h(n) (p. 2). Optimality guaranteed when h is admissible.
- **Greedy Best-First Search** — uses only h(n); fast but not optimal (p. 2).
- **Potential Field** — attractive (goal) + repulsive (obstacles) forces; suffers from local minima (p. 2).
- **Hierarchical Pathfinding** — decompose map into clusters; route at high level then refine inside zones (Sec. 3.1, p. 3). Cited as the technique used in Zelda: BotW (p. 6).
- **Jump Point Search (JPS)** — A* optimization on grid maps that "jumps" past symmetric/redundant nodes by recognizing critical "jump points" where path direction changes (Sec. 3.2, p. 3-4).
- **Bidirectional Search** — run search from both source and goal; meet in the middle (Sec. 4, p. 4).
- **D\*-Lite and LPA\*** — incremental replanning for dynamic maps; reuse prior search rather than recompute from scratch when terrain or goal changes (Sec. 5, p. 4-5).
- **Flow Field Pathfinding** — pre-compute one vector field over the whole map pointing toward the shared goal; all units follow the field (Sec. 6.1, p. 5). Cited use: Supreme Commander, StarCraft II (p. 5, 7).
- **Machine Learning / RL approaches** — train models on replay data to predict good paths or to adapt the heuristic dynamically (Sec. 7, p. 5-6). Cited use: Red Dead Redemption 2 (p. 8).

## Numerical params / hyperparams
The paper is essentially param-free. The only quantities mentioned:
- Figure 3 y-axis range "Time in milliseconds" 0-700 ms across 17 cycles for LPA* vs D*-Lite (p. 4) — qualitative chart, no numeric details, no source data, no methodology disclosed.
- A\* cost function literal: `f(n) = g(n) + h(n)`, with h required to be **admissible** (never over-estimate true cost) for optimality (p. 2).
- No grid size, no constants, no tuning parameters, no benchmark numbers, no thresholds, no node-count bounds, no memory figures.

That paucity is the single most relevant observation about this source: it gives no implementation-grade numbers for our heuristic.

## Reusable patterns for our heuristic
Heavy filtering required — Orbit Wars is **continuous 2D (100x100 plane), no static obstacles, no grid, sun is dynamic but predictable, planets rotate deterministically**. Almost every algorithm in this paper assumes a discrete grid. Reusable conceptual patterns only:

- **f(n) = g(n) + h(n) framing for target scoring (p. 2).** Treat candidate "missions" (capture-this-planet, defend-this-planet, intercept-that-fleet) as nodes. Score each as `cost_so_far + estimated_remaining_cost`. For Orbit Wars `g` could be ships-already-committed-to-mission and `h` could be expected-ships-needed-to-finish (garrison + projected reinforcements + sun-deflection cost). Pick the lowest-`f` mission. This is just A\* used as a target selector, not a navigator. Implements naturally in `src/orbit_wars/heuristic/target_scoring.py` (proposed module).
- **Admissibility hint (p. 2).** "It must be an admissible one indicating that it will never estimate the cost more than the actual cost to attain the specific goal." If we want our scoring function to give an *upper bound* on goodness (so we never over-promise on missions), the inverse principle helps: never over-estimate value (or equivalently, never under-estimate cost). Useful sanity-check for any scoring heuristic.
- **Hierarchical decomposition (Sec. 3.1, p. 3).** "Plan a high-level path within the larger areas first, then perform detailed search of sub regions." Translates to mission decomposition: top-level decision = which planet to target; mid-level = how many ships and from where; bottom-level = exact fleet-sizes per source-planet. Suggests a tiered architecture for our agent rather than a single monolithic scoring function.
- **Bidirectional Search (Sec. 4, p. 4).** Concept: search from both ends and converge. For Orbit Wars: when evaluating a planet capture, project both *forward* (our fleet's arrival time and surviving ships) and *backward* (when does the target's garrison grow large enough that capture becomes infeasible?). Their intersection determines a launch-window deadline. Cheap to compute and prevents launching a doomed expedition.
- **Real-time / Anytime / Incremental replanning (Sec. 5, p. 4-5).** D\*-Lite reuses prior search results when "the appearance of a new obstacle or the movement of the target." For us: when an enemy launches a fleet that invalidates a mission, don't re-plan from scratch — invalidate only the affected missions and re-rank. Useful if we cache a mission queue across turns (which CLAUDE.md notes is allowed via module-level cache keyed by `obs.player`).
- **Flow Field Pathfinding (Sec. 6.1, p. 5).** "Generates a grid interlinking the game map. Every square in this grid is a vector out to the goal. The objects that traverse through this grid just follow these vectors." For Orbit Wars: a static-target flow field is overkill (closed-form straight-line travel is exact in our continuous space) — but the *concept* of pre-computing a per-cell scalar field is useful for two derived quantities:
  - **Sun threat field** — for each (x,y) pre-compute a hazard score = inverse distance to sun's predicted future position over the next K turns. Aim points outside high-hazard cells.
  - **Influence field** — for each (x,y) pre-compute the dominant player by summing fleet-strength * f(distance). Targets in own-influence cells are safer; opportunities in contested cells are higher-EV.
  Both are O(W*H) one-time per turn (10000 cells for a 100x100 board); cheap inside 1s budget.
- **Potential field caveat (p. 2).** "However, this algorithm has the issue of local minima, where the units can end up in some rather less than ideal locations." If we use attractive/repulsive scalar fields for fleet routing around the sun, we must add an explicit deadlock-breaker (e.g., a small bias toward angular momentum around the sun) or units will stall at saddle points.
- **Greedy nearest-neighbor as a baseline (p. 2).** "Greedy Best-First Search can work pretty fast in terms of searching for a path; however, it does not provide the shortest path and may therefore be considered significantly less efficient than A\*." This describes our current `agent` exactly (the "nearest-planet sniper" baseline per CLAUDE.md). Confirms our intuition that pure greedy is a valid speed-optimized fallback but suboptimal; an A\*-style two-term scorer should beat it.

Patterns that are **not reusable** and would be a dead end to implement:
- JPS, Hierarchical-clustering, exact A\* over grid cells — Orbit Wars has no obstacles to navigate around (sun is the only one, and it's a single point), no grid graph at all. Fleet motion is straight-line in continuous 2D, so navigational pathfinding is trivial.
- D\*-Lite / LPA\* incremental graph repair — same reason; no graph to repair.

## Direct quotes / code snippets to preserve
- **A\* cost function (p. 2):** "It does this by minimizing the total cost function f(n) = g(n) + h(n), where f(n) is the cost to be minimized, g(n) is the direct cost, and h(n) is the sum of the holding cost and the constraint cost. Here f(n) denotes the total estimated cost including the cost of the cheapest solution up to n, g(n) is the actual cost of the path from the start node to node n, h(n) on the other hand is the heuristic estimation of the cost of the path from node n to the goal node."
- **Admissibility (p. 2):** "It must be an admissible one indicating that it will never estimate the cost more than the actual cost to attain the specific goal, thus making the path that was identified by the A\* algorithm to be optimal."
- **Hierarchical pathfinding rationale (p. 3):** "This multi-layered mechanism drastically lowers the computational burden paths results in quicker and precise routing. ... So for a very large open-world game the map will be split into cities -> neighborhoods, and then individual streets."
- **Potential-field local-minima warning (p. 2):** "However, this algorithm has the issue of local minima, where the units can end up in some rather less than ideal locations."
- **Flow-field rationale for many-unit RTS (p. 5):** "the game is a strategy game where players directly manage hundreds of units on the map, such as 'Supreme Commander'. That is moderated by the Flow Field Pathfinding since it enables all the units to see a precomputed vector field instead of computing it."
- **Bidirectional search efficiency (p. 4):** "Bidirectional Search is hence less expensive than unidirectional search because it constructs the paths from both ends of the problem and thus eliminates the nodes that are likely to be generated in both searches."

No code is given anywhere in the paper.

## Anything novel worth replicating
Sorted by perceived value (high to low):

1. **f = g + h as a target-scoring template (p. 2).** The single most transferable idea. Worth one afternoon to prototype a module that scores each candidate mission `(planet_target, source_planets, fleet_size)` as `g(commitment_cost) + h(estimated_cost_to_finish)` and picks the min. Beats nearest-neighbor sniper.
2. **Hierarchical decomposition of decision-making (Sec. 3.1).** Worth implementing as the agent's high-level architecture: stage 1 select objective, stage 2 select fleet composition, stage 3 select launch turn. Keeps each stage's branching factor small and inside the 1-second budget.
3. **Bidirectional-search analogy for launch-window deadlines (Sec. 4).** Forward-project our fleet, backward-project target's defensive growth, intersect for the latest viable launch turn. Cheap and prevents commit-then-fail expeditions.
4. **Flow-field-style pre-computed scalar fields for sun hazard and player influence (Sec. 6.1).** Replace per-fleet sun-distance checks with a once-per-turn 100x100 hazard map. O(10^4) cells, trivially fast in numpy.
5. **Incremental replanning for stale missions (Sec. 5).** Cache prior turn's mission ranking; on each new turn, only re-score missions whose inputs changed (a fleet was launched or arrived, a planet changed owner, sun position advanced). Reduces per-turn compute well below 1s ceiling.

Items 1-3 are de-facto already textbook AI-101 ideas; the paper's contribution is just naming them. Items 4-5 are slightly more interesting because they encode pre-computation + incremental update as the way to fit a 1-second-per-turn budget — which is exactly our Kaggle constraint.

## Open questions / things I couldn't determine
- The paper gives **zero implementation parameters** — no node-count limits, no heuristic-weight values, no time-budgets, no real benchmark numbers (Fig. 3 is unsourced). Cannot extract any tunable hyperparameter from this source.
- No discussion of **continuous-space pathfinding** (potential fields are mentioned but only briefly and without math). Orbit Wars does not have a grid, so the bulk of the paper's content (JPS, hierarchical clustering, D\*-Lite) does not apply directly. We need a different source for continuous-space target selection.
- No coverage of **multi-agent / adversarial pathfinding** beyond a one-line mention of MARL ([16], p. 9). Orbit Wars is 4-player free-for-all with simultaneous moves; this paper offers nothing on adversary modeling.
- No treatment of **resource economy or unit production trade-offs** — purely a navigation paper, not an RTS-strategy paper. For Orbit Wars our garrison-vs-launch trade-off (when to bank ships vs. when to attack) is uncovered here.
- The single-author Santa Clara University affiliation, light prose style, and lack of any new contribution suggest this is an undergraduate review article. Treat its claims as restatements of well-known textbook material rather than vetted research.

## Relevance to Orbit Wars (1-5)
**2 / 5.** Conceptually grounding (the f = g + h target-scoring template, hierarchical decomposition, and the pre-computed-field idea translate cleanly), but the paper's specific algorithms are grid-pathfinding solutions to a problem we do not have — Orbit Wars motion is straight-line in continuous 2D with one moving point-obstacle. Useful as orientation, weak as a source for parameters or implementation details.
