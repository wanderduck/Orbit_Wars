# MCTS overview

Reference document covering every file that constitutes the MCTS implementation
plus the testing / diagnostic toolchain used to develop and validate it.
Generated 2026-05-06 from the working state at commit `ae17929`.

## Caveat upfront

MCTS isn't "trained" in the ML sense — there's no parameter-learning loop.
What was built is a search algorithm whose runtime parameters (`MCTSConfig`)
are set manually, plus a battery of tests and diagnostic tools used to
validate and calibrate it during construction. The second table below
interprets "training" as the **development + validation + diagnostic
toolchain**.

## Table 1: MCTS runtime files

These are the files that constitute the MCTS implementation itself. All
under `src/orbit_wars/mcts/` unless noted.

| File | Status | Function |
|---|---|---|
| `src/main.py` | Pre-existing wrapper | Kaggle entry point. Defines `agent(obs)`, holds the module-level `MCTS_CFG`, and routes every turn through `mcts_agent`. The single file Kaggle's tarball runs. |
| `mcts/__init__.py` | Modified | Package surface — re-exports `MCTSConfig` and `mcts_agent` so callers don't need to know the internal layout. |
| `mcts/agent.py` | Pre-existing, used | Top-level `mcts_agent(obs, config)` entry. Guards against the env-positional-arg trap (CLAUDE.md gotcha), enforces the time-pressure fallback, and ALWAYS catches exceptions to fall back to heuristic so the env never receives invalid output. |
| `mcts/config.py` | Heavily extended | `MCTSConfig` frozen dataclass — every tunable knob (PW constants, FPU, UCB c, depth, time budget, ship fraction buckets) plus the option-2 additions (`use_token_variants`, `tokens_per_decision`, `max_launches_per_turn`, `long_tail_enabled`, `commit_position`). Frozen to prevent accidental per-turn mutation. |
| `mcts/extract.py` | Pre-existing, used | Converts a Kaggle `obs` (Struct or dict) into the typed `SimState` the simulator consumes. Includes `infer_num_agents_from_obs` for 2P-vs-4P detection. |
| `mcts/value.py` | Pre-existing, used | Leaf value estimator. Asset-share proxy with `production_horizon=8` weighting; returns a value in `[0, 1]` for backprop. Includes `is_terminal` predicate and the `EPISODE_STEPS=500` constant. |
| `mcts/ranking.py` | Rewritten (option 1) | LEGACY compound-variant action source. `ranked_actions_for` (lightweight ranker for inner nodes), `get_heuristic_action_for` (full heuristic call), `ranked_actions_with_heuristic` (root: v0=full heuristic + drop-one perturbations). Used when `cfg.use_token_variants=False`. |
| `mcts/node.py` | Pre-existing, used | LEGACY `MCTSNode` for compound-variant search. Per-`(player, action_idx)` UCB stats live AT this node. `JointAction` keying for children. |
| `mcts/search.py` | Heavily extended | The search engine. Public `search()` dispatches on `cfg.use_token_variants` between `_search_legacy` (M3 compound-variant) and `_search_tokens` (option 2 sub-tree). Holds PW (`_pw_action_count`), UCB+FPU (`_ucb_score`), token-variant helpers (`_filter_valid_token_indices`, `_ucb_select_token`, `_smmcts_token_iteration`). |
| `mcts/token.py` | NEW (option 2) | `LaunchToken(src, target, fraction_bucket)` dataclass + `COMMIT` sentinel + `token_id` bijective integer encoder for stats-dict keys. |
| `mcts/tokens.py` | NEW (option 2) | Token-space move-ordering function. `generate_ranked_tokens` calls the heuristic via `decide_with_decisions` and emits per-decision bucket tokens. Honors `cfg.commit_position` for the COMMIT placement. `extend_with_long_tail` is the optional ~530-token enumeration (off by default per Risk 1). |
| `mcts/serialize.py` | NEW (option 2) | Token sequence → env-format actions. `compute_angle_for_target` mirrors the heuristic's geometry (`safe_angle_and_distance` for static, `aim_with_prediction` for moving). `serialize_picks_to_env_actions` walks each player's pick sequence with running ship-pool deduction and `validate_move` checks. The Risk-2 correctness boundary. |
| `mcts/node_tokens.py` | NEW (option 2) | `SubNode` (per-env-turn launch sub-tree node, holds per-player UCB stats) and `MCTSNode` (env-turn-state node, owns its sub-tree via `subnode_cache` and committed children via `children`). `JointCommit` ordered-tuple type alias and `make_subnode_key` / `canonicalize_committed` helpers. |

**External dependencies the MCTS uses but does not own** (built earlier in
the project, not by the MCTS author):
`src/orbit_wars/sim/*.py` (the byte-faithful forward-model simulator that
calls `step()` to advance one env turn), `src/orbit_wars/heuristic/*.py`
(the move-ordering prior — the heuristic agent's per-launch scoring is what
MCTS treats as `f`), `src/orbit_wars/world.py` (intercept solver and
WorldModel forecasts), `src/orbit_wars/geometry.py` (sun-safe path /
distance math).

## Table 2: MCTS testing, diagnostics, and validation files

These are what was used to develop and verify the MCTS — there's no
parameter training, but this is the development toolchain that played the
equivalent role.

| File | Status | Function |
|---|---|---|
| `tests/test_mcts_m1_skeleton.py` | Modified | M1 skeleton tests — verifies `MCTSConfig` defaults, that `enabled=False` delegates transparently to the heuristic, that the env-positional-arg trap is caught, and that `enabled=True` returns a valid action list (this last one was an obsolete-test fix). |
| `tests/test_mcts_m3_pw_fpu.py` | NEW | M3 math validation: 16 unit tests covering Progressive Widening curve (`k = ⌈C·n^α⌉`), First-Play Urgency (unvisited returns `fpu_c` not `+inf`), and the documented "low-FPU starves exploration" failure mode. |
| `tests/test_mcts_perturbation_variants.py` | NEW (option 1) | 7 unit tests for `ranked_actions_with_heuristic` after the option-1 refactor — verifies v0=heuristic, v1=HOLD, v2..vk=drop-one ordered by heuristic-confidence-ascending, k-budget truncation, and no leakage of lightweight-ranker variants. |
| `tests/test_mcts_token.py` | NEW (option 2) | 13 unit tests for `LaunchToken` equality, frozenness, COMMIT sentinel behavior, and `token_id` bijective encoding (collision-free across plausible game-config range). |
| `tests/test_mcts_tokens.py` | NEW (option 2) | 12 unit tests for `generate_ranked_tokens`: empty heuristic output, COMMIT placement (both `"first"` and `"last"`), `tokens_per_decision` sizing, bucket-distance ordering, defensive source-id filtering, decision-rank preservation, long-tail behavior. |
| `tests/test_mcts_serialize.py` | NEW (option 2 — RISK-2 GATE) | 14 unit tests in two layers. **Layer 1 (angle parity):** `compute_angle_for_target` matches `safe_angle_and_distance` / `aim_with_prediction` for static, orbiting, and comet targets. **Layer 2 (serializer correctness):** bucket→ships resolution, ship-pool deduction across multiple picks from same source, COMMIT-breaks-loop, invalid-token silent drop, env-format wrapper. |
| `tests/test_mcts_node_tokens.py` | NEW (option 2) | 21 unit tests for `SubNode` per-player stats, `all_committed` predicate, sub-node key canonicalization (order matters — pick ordering changes ship-pool deduction), `MCTSNode.root_subnode` caching across iterations, and arity-aware sub-tree initialization for 2P vs 4P. |
| `tests/test_mcts_search_tokens.py` | NEW (option 2) | 14 unit tests for the search loop: `_filter_valid_token_indices` ship-pool deduction, `_ucb_select_token` argmax behavior, the legacy-vs-token search dispatcher correctness, and end-to-end `_search_tokens` smoke (real Simulator on a small synthetic state, verifies no exceptions and reasonable debug output). |
| `src/tools/mcts_picks_diag.py` | NEW | Per-turn diagnostic: runs MCTS-as-P0 vs `src/main.py`, captures the search debug dict each turn, and aggregates the variant-pick distribution (legacy mode) or token-sequence distribution (option-2 mode). `--fpu-c`, `--max-depth`, `--use-token-variants` CLI flags for calibration sweeps. The tool that surfaced the M3 "100% v0" finding and the option-2 "99% COMMIT" finding. |
| `src/tools/mcts_local_ab.py` | NEW | Paired-seat A/B harness for MCTS-vs-heuristic. Runs each seed twice (MCTS as P0 then P1) inside one Python process so env's RNG-state stream is matched per CLAUDE.md `phase2_step4_findings.md`. Reports per-seat outcomes plus aggregate winrate; gates on ≥50% paired wr. |
| `docs/research_documents/2026-05-06-mcts-algorithm-design.md` | NEW (revised v2) | The literature-grounded design doc that drove M2/M3 (canonical SM-MCTS + PW + FPU + decoupled UCT per Aljabasini 2021). Closed open question 3 from the original design's "candidate" definition. |
| `docs/research_documents/2026-05-06-mcts-option2-tokens-design.md` | NEW (subagent) | The option-2 architectural revision — single-launch-token action space, per-env-turn launch sub-trees, sub-node-level UCB stats, robust child via most-visited COMMITTED CHILD. Includes risk register (Risk 2 = serialization correctness, gated by `tests/test_mcts_serialize.py`). |

**Note on the heuristic CMA-ES tuner:**
`src/tools/modal_tuner.py` and `src/tools/heuristic_tuner_param_space.py`
(plus the overhaul versions in
`src/orbit_wars/heuristic/heuristic_overhaul/`) tune `HeuristicConfig`,
**not `MCTSConfig`**. Better-tuned heuristic params do indirectly help MCTS
because the heuristic is the move-ordering prior `f` that MCTS samples
from — but it's not training MCTS itself. If you wanted to apply the same
CMA-ES infrastructure to `MCTSConfig` (e.g., learn `fpu_c`, `widen_c`,
`widen_alpha`, `commit_position`, `tokens_per_decision`), the tuner would
need a parallel param-space file pointing at `MCTSConfig` fields plus a
fitness function that runs MCTS-vs-heuristic games. That work is not yet
built.
