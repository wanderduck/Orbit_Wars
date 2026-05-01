# Paper 9 — Pathfinder Agent Research (Student Comparison Paper)

**Source PDF:** `paper9.pdf` in this directory.

## Executive summary

A very short student-style write-up comparing Dijkstra's algorithm to tabular Q-learning on a single 20-node random graph with edge weights (wait times) and node weights (compute resources), reporting that Q-learning peaks at ~95% success around 350 episodes then degrades to ~50%. **It is not a hybrid RL+heuristic method** — it pits the two against each other on toy graph routing — and offers essentially nothing transferable to Orbit Wars.

## 1. Title, authors, venue/year, document type
"Comparing Pathfinding Agents: Heuristic vs. Reinforcement Learning" by Sohan Mekala (p.1, cover). No venue, no year, no abstract, no affiliation — appears to be an undergraduate or even high-school class paper / informal write-up. Total length: 4 content pages + cover; 4 references (Cormen, Dijkstra 1959, Schrijver, Sutton & Barto). Code link: github.com/SohanMekala/Pathfinder-Agent-Research (p.2). **Document type: short student report, not a peer-reviewed paper.**

## 2. Problem setting / domain
Single-agent shortest-path on a static, randomly generated graph of **20 nodes** (p.2). Edges carry "wait times" (traversal cost); nodes carry "computing resources" (capacity that requests consume). A "request" is (start, end, required compute). A path is *successful* if it reaches the goal while satisfying the resource requirement and not exceeding a max duration (p.2). Motivated as a gap in classical shortest-path: Dijkstra optimizes edge cost only, not node-capacity constraints (p.1).

## 3. Method
Two competing approaches, both solving the same request set (p.2):
- **Heuristic:** Dijkstra's algorithm "adapted to ensure paths meet computing resource requirements and do not exceed maximum duration constraints" (p.2). No equations, no description of how the constraint adaptation works (presumably edge filtering or post-hoc validation — not specified).
- **RL:** Tabular **Q-learning** "updating a Q-table based on rewards and penalties related to resource availability and path duration" (p.2). No state representation, no action space, no reward formula, no hyperparameters (α, γ, ε), no exploration schedule given. Sutton & Barto cited generically.

Evaluation metric: success rate = successful requests / total requests, swept over training episode counts {100, 200, 300, 400, 500} (p.2 figure).

## 4. Key results
From the figure and p.3 narrative:
- Heuristic (Dijkstra): flat ~50% success across all episode counts (p.3).
- Q-learning: ~25% at 100 episodes, crosses heuristic at ~150-200 episodes, peaks ~95% near 350 episodes, then **degrades to ~50% at 500 episodes** (p.3).
- Authors interpret the post-peak drop as "potential overfitting or learning instabilities when training is extended too far" (p.3).

No baselines beyond these two. No statistical significance, no error bars, n=1 graph, n=1 seed implied. The 50% Dijkstra ceiling suggests the constraint-adapted variant is rejecting roughly half of feasible requests — likely the "adaptation" is naive (e.g. filtering edges by some node criterion that throws out viable paths).

## 5. Heuristic-RL integration
**None.** The paper compares the two as *alternatives*, not a hybrid. There is no policy prior, reward shaping from heuristic, action mask, curriculum, search-tree pruning, exploration guide, or self-play. **This is the exact opposite of what the research bucket calls for.**

## 6. Strengths / limitations (as authors describe)
Authors say RL has "superior adaptability" at peak but "is heavily dependent on the number of training episodes" and recommends the heuristic when "reliability is prioritized over maximum efficiency" (p.3). They suggest future work on maintaining RL performance at higher episode counts and on more complex graphs (p.3). Unstated but glaring: no significance testing, single graph, no hyperparameter discussion, peak-vs-degraded interpretation could equally be a single-seed artifact, and the "Q-learning post-peak collapse" pattern is not theoretically grounded (tabular Q-learning with appropriate ε-decay should not catastrophically degrade — this hints at a bug or non-decaying ε in the implementation).

## 7. Applicability to Orbit Wars
**Essentially zero.** Reasons:
- Wrong problem class: single-agent static graph routing vs. 4-player real-time strategy with hidden-information dynamics, moving targets, fleet combat resolution, episode-level credit assignment.
- Wrong method scale: tabular Q-learning on 20 states cannot represent Orbit Wars' continuous-ish positional state, multi-planet ownership vector, or fleet trajectories.
- Not a hybrid: the paper offers no integration pattern to copy.
- The one transferable observation — "tabular Q-learning can degrade past an optimum, monitor early stopping" — is already common knowledge from Sutton & Barto and doesn't justify a prototype.

**1-2 week prototype feasibility:** Not applicable. There is nothing in this paper worth implementing. **Recommendation: skip — do not allocate any of the 7-week budget to following this paper's methodology.**

## 8. What couldn't be determined
State/action encoding for the Q-table; reward formula; exploration schedule (the post-peak degradation strongly implies non-decaying ε but is not confirmed); how Dijkstra was "adapted" for node constraints (the 50% flat ceiling is suspicious and suggests an implementation issue rather than a fundamental Dijkstra limitation); number of seeds/repetitions per data point; venue, year, and author affiliation; whether the GitHub code is still accessible and what it actually contains.
