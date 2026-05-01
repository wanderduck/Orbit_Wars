---
source_url: https://www.kaggle.com/code/rahulchauhan016/orbit-wars-target-score-2000-4
author: rahulchauhan016
slug: orbit-wars-target-score-2000-4
title_claim: '"Orbit Wars" / "Target Score: 2000.4" (cell 49 banner; not achieved)'
ladder_verified: rank 803, score 691.2
pulled_on: 2026-05-01
pull_command: uv run kaggle kernels pull rahulchauhan016/orbit-wars-target-score-2000-4
---

# rahulchauhan016/orbit-wars-target-score-2000-4

## Architecture in one sentence
A 50-cell kitchen-sink notebook that stacks MCTS + beam search + counterfactual risk pruning + a 7-feature evaluator + opponent-history model + diplomacy heuristic + 14-64-32-1 NumPy MLP + 7 strategy templates behind one `elite_bot_v5(obs, config=None)` priority stack (cell 35), then auto-exports `submission.py` via `inspect.getsource` (cell 49).

## Notable techniques
- Iterative lead-aim (cell 9): 6-iter fixed-point on `eta = dist / fleet_speed(ships)` then re-predicts target; `safe_aim` sweeps ±{0.08, 0.16, 0.28, 0.45} rad to dodge sun. Lead-aim only fires when `is_inner(dst)` (`dist<30`); outer planets get naive `angle_to`.
- MCTS UCB1 (cell 15): 420 ms budget, candidate pool restricted to nearest-7 enemies/neutrals per source, depth-10 random rollouts using a custom `sim_step` plus 7-component evaluator.
- Counterfactual risk filter (cell 27): "enemy sends half ships to my weakest" sim prunes candidate action sets at threshold -80.
- Phase-gated 7-candidate planner (cell 33): early/mid/late + aggro/defend/diplo/counter; budget reserves `max(production*4, threat+10)` then sends 70% of surplus.
- `_tgt(f)` (cell 7) infers ANY fleet's destination by bearing alignment within 0.28 rad to the nearest planet on that bearing.

## Visible evidence
Cell 35 entrypoint (condensed):
```python
def elite_bot_v5(obs, config=None):
    global GLOBAL_OPP_V5
    try:
        state = GameState(obs)
        if not state.my_pl: return []
        # 1. Fleet interception (<100ms)
        # 2. MCTS search (420ms)
        # 3. Beam search supplement
        # 4. Strategy candidates (CFR-filtered)
        # 5. Neural gate: try: nv=NEURAL.predict(state) except: pass
        # 6. Comet opportunism
```
Cell 13 evaluator weights: `WS=1.0  WP=46.0  WC=20.0  WR=-2.8  WB=9.0  WF=0.6  WN=12.0`.
Cell 49 wrapper: `def agent(obs, config=None): return elite_bot_v5(obs, config)`.

## Relevance to v1.5G
- Lead-aim (cell 9, 6 iters) is essentially our `aim_with_prediction`. Nothing new.
- The CFR pruning idea (cell 27) is directionally interesting against v1.5G's defense-aware planner — score every candidate launch by a one-shot enemy retaliation sim and drop the worst — but their concrete check is naive (half enemy ships at our weakest, no rotation, no path collision).
- Evaluator weights (`WP=46` vs `WS=1`) imply production growth dominates ship-count by ~46x in their forward sim. Empirical knob worth comparing.
- `_tgt(f)` infers ANY fleet's destination by bearing — could in principle augment v1.5G's threat detection (we currently know only OUR own fleet destinations).

## What couldn't be determined
- Output cells weren't executed/inspected; cell 45 benchmark `all_res` is unverified. No measured win rate in the static notebook.
- Auto-built `submission.py` likely runs but with neural gate silently dead: `NeuralVal` is NOT in cell 49's `CLASSES` export list and `NEURAL = NeuralVal()` is never written to submission.py. The `try/except: pass` masks the AttributeError. The 691.2 ladder may include this dead branch.
- Title says 2000.4; ladder shows 691.2.
