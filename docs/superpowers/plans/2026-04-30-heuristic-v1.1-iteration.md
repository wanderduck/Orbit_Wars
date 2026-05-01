# Heuristic v1.1 Iteration Plan — Diagnostic-First Improvement

**Date:** 2026-04-30
**Driver:** Research findings at `docs/research_documents/research_findings.md` (synthesis of 8 sources, 2 scoring 4/5)
**Predecessor:** `docs/superpowers/plans/2026-04-30-orbit-wars-multi-agent-orchestration.md` (built v1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift heuristic from current ~30-40% win rate vs. `random` to **≥80% over 20 seeds** by applying the four Tier A research recommendations in diagnostic-driven order.

**Architecture:** Three sequential layers, each gated by a tournament check before proceeding to the next. Build diagnostic harness first to identify the dominant failure mode empirically; apply targeted fixes one at a time; validate each fix in a 10-seed tournament before stacking the next; finalize with a 20-seed acceptance test before repacking the submission.

**Tech Stack:** existing — Python 3.13, `kaggle-environments`, pytest, the `WorldModel` and `aim_with_prediction` infrastructure built in v1. New deps possible: `scipy.optimize.linear_sum_assignment` (already in scipy via `scipy-stubs`; verify on first use).

---

## Goal & success criteria

- **Primary goal:** beat the built-in `random` opponent (which IS launching half-ships at random angles; not a no-op as I initially assumed) **≥ 80% over 20 seeds**.
- **Secondary goal:** beat the original sniper baseline (`max(target.ships+1, 20)` from `docs/internal/findings/E5-bovard-getting-started.md` cell 6) ≥ 60% over 20 seeds.
- **Tertiary goal:** all 37 unit tests still pass; no regression in pack/G4 smoke test.

### Win-rate gates per phase

Each fix must move the win-rate vs `random` by a measurable margin before the next fix is added:

| Phase | Gate | Action if gate fails |
|-------|------|---------------------|
| After diagnostic (Phase 2) | Identify dominant failure mode (≥ 50% of failed launches share a single cause) | If failure modes are diffuse, escalate to user for direction |
| After Fix #1 (Phase 4) | Win rate ≥ 50% over 10 seeds | Revert; try a different fix |
| After Fix #2 (Phase 6) | Win rate ≥ 65% over 10 seeds | Revert; debug Fix #1 + #2 interaction |
| After Fix #3 (Phase 8) | Win rate ≥ 75% over 10 seeds | Revert; the fix is over-tuning vs marginal-utility |
| After Fix #4 (Phase 10) | Win rate ≥ 80% over 20 seeds | Document remaining gap; ship anyway if ≥ 75% |

**Reverts go through git revert/checkout on the relevant file(s); user owns commits, so reverts are by file replacement.**

---

## Current baseline (measured)

- v1 (commit-pending) — `src/orbit_wars/heuristic/strategy.py` minimal sniper-with-WorldModel-sizing
- 10-seed test (`uv run python -c "..."` with `main.agent` vs `'random'`):
  - Unseeded global RNG: 3W / 7L (30%)
  - With `random.seed(42)`: 1W / 9L (10%)
  - **High variance from global RNG — random_agent uses `random.uniform` for angle**
- Final-state observation in losing games: P0 ends with 1 planet (just home); P1 ends with 24-39 planets and 39+ fleets in flight
- 37/37 unit tests pass; G4 submission smoke test passes

---

## Operating ground rules

1. **Diagnostic before fix.** No strategy edits before Phase 2 produces a failure-mode summary. The research explicitly warns against this pattern (R5 calls it Greedy Best-First-style local-optima chasing — applies to debugging too).
2. **One change per phase.** Each fix lands and is validated independently. No bundling — we cannot attribute a regression if two changes ship together.
3. **Git policy unchanged from v1 plan**: orchestrator does not run `git add` / `commit` / `push`. User commits at natural boundaries; reverts during this iteration are by file overwrite.
4. **Reproducibility**: every tournament includes `random.seed(42)` in the runner so opponent behavior is deterministic. Plus 20 different env seeds for variance reduction.
5. **Time budget per phase**: target ~30 min wall-clock. If a phase exceeds 60 min without progress, surface to user before continuing.
6. **No new dependencies** without an explicit step adding them via `uv add`. (Possible additions: `scipy` for `linear_sum_assignment` — already pulled in via `scipy-stubs`.)
7. **All experiments log to `docs/iteration_logs/v1.1/`** so we have a paper trail.

---

## File structure (new + modified)

| Path | Created/Modified | Phase | Responsibility |
|------|------------------|-------|----------------|
| `docs/iteration_logs/v1.1/` | new dir | 0 | Hold all experiment outputs |
| `tools/diagnostic.py` | new | 1 | Instrumented agent wrapper that logs every launch |
| `docs/iteration_logs/v1.1/diagnostic_seeds_0-4.json` | new | 2 | Per-launch records for 5 seeds |
| `docs/iteration_logs/v1.1/diagnostic_summary.md` | new | 2 | Aggregated failure-mode analysis |
| `src/orbit_wars/heuristic/strategy.py` | modified | 3 or 5 | Apply A.2 (intercept-only) and/or A.1 (f=g+h) |
| `src/orbit_wars/heuristic/targeting.py` | modified | 3 or 5 | Apply multi-tier scoring if A.1 selected |
| `src/orbit_wars/heuristic/assignment.py` | new | 7 | Hungarian fleet→target dispatch |
| `src/orbit_wars/heuristic/config.py` | modified | 9 | Add `loss_aversion_lambda: float = 1.5` |
| `tools/cli.py` | modified | 11 | Extend `ladder` command with config A/B testing |
| `docs/iteration_logs/v1.1/results_phase{4,6,8,10,11}.md` | new | per phase | Tournament results |

---

## Phase 0: Pre-flight & baseline confirmation

### Task 0.1: Verify current state

- [ ] **Step 1:** Confirm 37 tests pass.
  Run: `uv run pytest -q`. Expect: `37 passed`.

- [ ] **Step 2:** Confirm submission packs cleanly.
  Run: `uv run orbit-play pack`. Expect: SHA-256 printed, smoke test passes.

- [ ] **Step 3:** Re-measure baseline win rate against `random` to anchor improvements.
  Run: a 10-seed test with `random.seed(42)` set globally (use the same script as in the previous iteration's measurements; preserve in `tools/diagnostic.py` later).
  Record: `wins / 10` and per-seed results in `docs/iteration_logs/v1.1/baseline.md`.

- [ ] **Step 4:** Create `docs/iteration_logs/v1.1/` directory.
  Run: `mkdir -p docs/iteration_logs/v1.1`

---

## Phase 1: Build diagnostic harness

### Task 1.1: Instrument the agent for per-launch logging

The diagnostic wraps our agent. For every launch, it captures:
- `step`: turn number
- `src_id`, `src_x`, `src_y`, `src_ships_pre_launch`
- `target_id`, `target_owner`, `target_ships_at_launch`, `target_x`, `target_y`, `target_radius`, `target_is_static`, `target_is_comet`
- `ships_sent`, `angle`, `predicted_eta`
- (resolved at fleet arrival turn): `did_capture` (bool), `arrival_turn`, `actual_target_owner_at_arrival`, `actual_target_ships_at_arrival`, `failure_reason` ∈ {None, 'sun', 'oob', 'combat-loss', 'no-target-at-arrival', 'arrived-but-already-ours'}

**Files:**
- Create: `tools/diagnostic.py`

- [ ] **Step 1: Write the launch logger**

```python
# tools/diagnostic.py
"""Instrument agent.py to log every launch with arrival-resolution details.

Run via: `uv run python -m tools.diagnostic --seeds 0,1,2,3,4 --out docs/iteration_logs/v1.1/`
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import typer
from kaggle_environments import make

from orbit_wars.geometry import is_static_planet
from orbit_wars.heuristic.strategy import _decide
from orbit_wars.heuristic.config import HeuristicConfig
from orbit_wars.state import ObservationView


@dataclass
class LaunchRecord:
    seed: int
    step: int
    src_id: int
    src_x: float
    src_y: float
    src_ships_pre_launch: int
    target_id: int
    target_owner: int
    target_ships_at_launch: int
    target_x: float
    target_y: float
    target_radius: float
    target_is_static: bool
    target_is_comet: bool
    ships_sent: int
    angle: float
    predicted_eta: int  # 0 if unknown
    # Filled at arrival:
    did_capture: bool | None = None
    arrival_turn: int | None = None
    actual_target_owner_at_arrival: int | None = None
    actual_target_ships_at_arrival: int | None = None
    failure_reason: str | None = None


def diagnose_seed(seed: int) -> list[LaunchRecord]:
    """Run main.agent vs 'random' for one seed, log every launch + outcome."""
    env = make('orbit_wars', debug=False, configuration={'seed': seed})
    records: list[LaunchRecord] = []
    pending: dict[tuple[int, int], LaunchRecord] = {}  # (fleet_id, src_id) -> record

    cfg = HeuristicConfig.default()

    def instrumented_agent(obs):
        view = ObservationView.from_raw(obs)
        moves = _decide(obs, cfg)
        # Log each move
        for m in moves:
            sid, angle, ships = m
            src = next((p for p in view.my_planets if p.id == sid), None)
            if src is None:
                continue
            # Find the most-likely target by computing angle-of-nearest-planet (heuristic — strategy doesn't expose its choice)
            best = None
            best_align = -2.0
            for p in view.planets:
                if p.id == sid:
                    continue
                ang_to_p = math.atan2(p.y - src.y, p.x - src.x)
                # Cosine similarity of angles
                align = math.cos(angle - ang_to_p)
                # Closer planets prefered if alignment is OK
                if align > 0.95:  # ~18 degree cone
                    if best is None or align > best_align:
                        best = p
                        best_align = align
            if best is None:
                continue
            rec = LaunchRecord(
                seed=seed,
                step=view.step or len(env.steps) - 1,
                src_id=sid,
                src_x=src.x, src_y=src.y,
                src_ships_pre_launch=int(src.ships),
                target_id=best.id,
                target_owner=best.owner,
                target_ships_at_launch=int(best.ships),
                target_x=best.x, target_y=best.y,
                target_radius=best.radius,
                target_is_static=is_static_planet(best.x, best.y, best.radius),
                target_is_comet=view.is_comet(best.id),
                ships_sent=int(ships),
                angle=float(angle),
                predicted_eta=0,  # filled if we can compute below
            )
            records.append(rec)
            pending[(sid, best.id)] = rec
        return moves

    env.run([instrumented_agent, 'random'])

    # Resolve arrivals: for each launch, walk forward looking for the fleet to arrive
    # (For now, just compare final-state ownership of each target to launch-time)
    for rec in records:
        # Look at final state: did target_id end up ours?
        final_obs = env.steps[-1][0].observation
        target_planet = next((p for p in final_obs.planets if p[0] == rec.target_id), None)
        if target_planet is None:
            rec.failure_reason = 'no-target-at-arrival'
            rec.did_capture = False
        else:
            rec.actual_target_owner_at_arrival = target_planet[1]
            rec.actual_target_ships_at_arrival = target_planet[5]
            rec.did_capture = (target_planet[1] == 0)  # we are player 0

    return records


app = typer.Typer()


@app.command()
def run(seeds: str = '0,1,2,3,4', out: str = 'docs/iteration_logs/v1.1/'):
    """Run diagnostic across multiple seeds; write JSON + summary."""
    seed_list = [int(s.strip()) for s in seeds.split(',')]
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[LaunchRecord] = []
    for s in seed_list:
        recs = diagnose_seed(s)
        all_records.extend(recs)
        print(f'seed={s}: {len(recs)} launches, {sum(1 for r in recs if r.did_capture)} captures')

    json_path = out_dir / f'diagnostic_seeds_{seed_list[0]}-{seed_list[-1]}.json'
    json_path.write_text(json.dumps([asdict(r) for r in all_records], indent=2, default=str))
    print(f'Wrote {len(all_records)} records to {json_path}')


if __name__ == '__main__':
    app()
```

- [ ] **Step 2: Verify the diagnostic runs**

Run: `uv run python -m tools.diagnostic run --seeds 0`
Expect: it prints `seed=0: NN launches, MM captures` and writes a JSON.

**Important caveat:** the "target inference" in `instrumented_agent` is heuristic — `_decide` doesn't return *which target* it picked, only the angle. We infer by finding a planet whose angle-from-src aligns with the launched angle (cosine > 0.95, ~18° cone). This will be approximately right but may misattribute when two planets are co-aligned. Accept for now; if Phase 2 results are noisy, refactor `_decide` to return tagged moves.

---

## Phase 2: Run diagnostic and identify failure mode

### Task 2.1: Multi-seed diagnostic run

- [ ] **Step 1: Run diagnostic over 5 seeds**
  Run: `uv run python -m tools.diagnostic run --seeds 0,1,2,3,4`
  Expect: ~50-200 launches per seed; total ~250-1000 records.

- [ ] **Step 2: Aggregate by failure mode**

Write a small analysis script (inline in next bash call or in `tools/diagnostic.py` as `analyze` command):
- Total launches
- Captures (did_capture == True)
- Misses by category:
  - Target was static: captures vs misses
  - Target was orbiting (not comet): captures vs misses
  - Target was comet: captures vs misses
- Misses by failure_reason
- Distribution of `target_is_static` for misses

Write the summary to `docs/iteration_logs/v1.1/diagnostic_summary.md`.

- [ ] **Step 3: Identify dominant failure mode**

Decision rule:
- If **>60% of missed launches were on orbiting/comet targets** → primary fix is **A.2 intercept-only** (Phase 3).
- If **>60% of missed launches were on static targets and ships were sufficient at launch** → primary fix is **A.1 multi-tier scoring** (i.e., we're picking the wrong targets).
- If **misses are diffuse**: surface to user — may need a different fix.

Document the decision in `docs/iteration_logs/v1.1/diagnostic_summary.md` with a `## Decision` section.

---

## Phase 3: Apply Fix #1 (whichever the diagnostic indicates)

### Path 3.A: If diagnostic indicates "fleets miss orbiting targets"

**Files:** modify `src/orbit_wars/heuristic/strategy.py`

- [ ] **Step 1: Refactor `_try_launch` to be intercept-only for moving targets**

Currently `_try_launch` falls back to `plan_safe_launch` (current-position aim) when intercept fails. Change to:

- For static, non-comet targets: use `plan_safe_launch` as today (no intercept needed).
- For orbiting or comet targets: ONLY use `aim_with_prediction`. If it returns `None`, **skip the target** (do not fall back).

Specifically, in the `else` branch of `_try_launch` for moving targets:

```python
intercept = aim_with_prediction(
    src=src, target=target, ships=ships_send,
    initial=initial,
    angular_velocity=view.angular_velocity,
    comet_path=comet_path,
    comet_path_index=comet_idx,
)
if intercept is None:
    return None  # SKIP — do not fall back to plan_safe_launch for moving targets
angle, eta, _xy = intercept
```

- [ ] **Step 2: Run unit tests**
  Run: `uv run pytest -q`. Expect: 37 passed.

- [ ] **Step 3: Run 10-seed tournament against `random`**
  Run: same script as baseline, measure win rate.
  Save: `docs/iteration_logs/v1.1/results_phase4_intercept_only.md`

### Path 3.B: If diagnostic indicates "wrong target selection"

**Files:** modify `src/orbit_wars/heuristic/targeting.py` and `strategy.py`

- [ ] **Step 1: Replace the linear-sum scoring with multi-tier `f = g + h`**

In `targeting.py:score_target`, change from:

```python
total = w_roi * roi + w_dist * dist_score + w_prod * prod_score + ...
```

to:

```python
# g = commitment cost
g = ships_needed_now + travel_time_cost(eta)

# h = expected remaining cost (admissible — never overestimate)
h = (
    expected_defense_growth_during_transit(target, eta)
    + sun_collision_risk_along_path(src, target) * SUN_PENALTY
    + opportunity_cost_of_skipping(other_targets)
)

# Multi-tier value (orders-of-magnitude separation)
value = (
    1e6 * (1 if target_is_decisive_capture(target) else 0)
    + 1e3 * production_value(target, remaining_steps - eta)
    + 1.0 * positional_value(target, view, world)
)

# Score: higher value / lower cost = better
return value / max(1.0, g + h)
```

- Use `1e6` etc as named constants in `config.py` with comments referencing R2 §"Hierarchical, multiplicatively-separated value tiers".

- [ ] **Step 2: Update `strategy.py`** to use the new score for target ranking (still nearest-first as a tiebreaker if scores are within 1%; this catches the case where the multi-tier scoring is degenerate).

- [ ] **Step 3: Run unit tests**
  Run: `uv run pytest -q`. Expect: 37 passed.

- [ ] **Step 4: Run 10-seed tournament**
  Save results to `docs/iteration_logs/v1.1/results_phase4_multi_tier_scoring.md`

---

## Phase 4: Validate Fix #1

- [ ] **Step 1: Compare to baseline**

If win rate ≥ 50%: Gate **PASSED**. Mark phase complete; move to Phase 5.
If win rate < 50%: Gate **FAILED**. Options:
  a. Revert the change (`git checkout HEAD -- src/orbit_wars/heuristic/`) and try the OTHER fix (3.A → 3.B or vice versa).
  b. Surface to user.

- [ ] **Step 2: Tournament also vs sniper baseline (sanity check)**

Run a 10-seed tournament where opponent = the sniper from `docs/internal/findings/E5-bovard-getting-started.md` cell 6.
Save in same results file.
This catches the case where we improve vs random but regress vs sniper (likely if our change favors crashing into well-defended planets).

---

## Phase 5: Apply Fix #2 (the OTHER Tier A.1/A.2)

Whichever of A.1 / A.2 wasn't applied in Phase 3.

- [ ] **Step 1:** Apply the other fix following the same sub-steps as Phase 3.
- [ ] **Step 2:** Run unit tests.
- [ ] **Step 3:** Run 10-seed tournament. Save to `docs/iteration_logs/v1.1/results_phase6_<both_fixes>.md`.

---

## Phase 6: Validate Fix #2

- [ ] **Step 1: Compare to Phase 4 result**

Gate: ≥ 65% win rate over 10 seeds.

If pass: continue to Phase 7.
If fail: the two fixes interact poorly. Revert Fix #2; investigate; surface to user.

---

## Phase 7: Apply Fix #3 — Hungarian assignment

**Files:** create `src/orbit_wars/heuristic/assignment.py`; modify `strategy.py`

- [ ] **Step 1: Implement the assignment module**

```python
# src/orbit_wars/heuristic/assignment.py
"""One-to-one optimal fleet→target dispatch via the Hungarian algorithm.

Replaces the per-source greedy "for src in my_planets: pick best target" loop.
For N owned planets and M sun-safe affordable targets, build a cost matrix
and solve in O((N+M)^3) via scipy.optimize.linear_sum_assignment.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..state import Planet
from ..world import WorldModel
from .config import HeuristicConfig


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    src_id: int
    target_id: int
    angle: float
    ships: int


def assign_launches(
    candidates: list[tuple[int, int, float, int, float]],  # (src_id, target_id, angle, ships, score)
    *,
    config: HeuristicConfig,
) -> list[LaunchPlan]:
    """Compute one-to-one optimal assignment from candidate (src, target) pairs.

    `candidates` is a flat list of all viable (src, target, angle, ships, score)
    that passed gating in `strategy.py`. We treat each unique src as a row and
    each unique target as a column, with cost = -score (Hungarian minimizes).
    Sources not assigned to any target produce no launch.
    """
    if not candidates:
        return []

    src_ids = sorted({c[0] for c in candidates})
    target_ids = sorted({c[1] for c in candidates})
    src_idx = {s: i for i, s in enumerate(src_ids)}
    tgt_idx = {t: j for j, t in enumerate(target_ids)}

    # Cost matrix: rows = sources, cols = targets. Higher score = lower cost (negate).
    INF_COST = 1e18
    cost = np.full((len(src_ids), len(target_ids)), INF_COST)
    detail = {}  # (i, j) -> (angle, ships)
    for src_id, tgt_id, angle, ships, score in candidates:
        i, j = src_idx[src_id], tgt_idx[tgt_id]
        if -score < cost[i, j]:
            cost[i, j] = -score
            detail[(i, j)] = (angle, ships)

    # Pad to square (Hungarian assumes square matrix; but linear_sum_assignment handles rectangular)
    row_ind, col_ind = linear_sum_assignment(cost)

    plans: list[LaunchPlan] = []
    for i, j in zip(row_ind, col_ind):
        if cost[i, j] >= INF_COST:
            continue  # this pair was never a real candidate
        angle, ships = detail[(i, j)]
        plans.append(LaunchPlan(
            src_id=src_ids[i],
            target_id=target_ids[j],
            angle=angle,
            ships=ships,
        ))
    return plans
```

- [ ] **Step 2: Update `strategy.py` to collect all viable (src, target) candidates first, then assign**

```python
# In strategy._decide, after gathering threats and used_ships:
candidates: list[tuple[int, int, float, int, float]] = []
for src in view.my_planets:
    available = int(src.ships) - used_ships.get(src.id, 0) - cfg.home_reserve
    if available < cfg.min_launch:
        continue
    for target in target_planets:
        result = _try_launch(src, target, view, world, cfg, available)
        if result is None:
            continue
        angle, ships = result
        score = score_target(src, target, eta=eta, ships_needed=ships, view=view, world=world, config=cfg, mission='capture')
        candidates.append((src.id, target.id, angle, ships, score))

from .assignment import assign_launches
plans = assign_launches(candidates, config=cfg)
for plan in plans:
    moves.append([plan.src_id, plan.angle, plan.ships])
```

- [ ] **Step 3:** Add a unit test for `assignment.py` (3-source × 4-target toy case where greedy and Hungarian differ).

- [ ] **Step 4:** Run all tests. Expect: 38 passed (1 new).

- [ ] **Step 5:** Run 10-seed tournament. Save to `results_phase8_hungarian.md`.

---

## Phase 8: Validate Fix #3

Gate: ≥ 75% win rate over 10 seeds.

- [ ] **Step 1:** If fail, revert and investigate. Hungarian could regress if our scores are poorly normalized — multi-tier values may dwarf per-source variation. In that case, normalize per-source before assigning.

---

## Phase 9: Apply Fix #4 — loss-aversion λ

**Files:** modify `src/orbit_wars/heuristic/config.py` and `targeting.py`

- [ ] **Step 1: Add config**

```python
# In HeuristicConfig:
loss_aversion_lambda: float = 1.5  # was 1.0 (symmetric) — R5/R6/R8 all favor asymmetric
```

- [ ] **Step 2: Apply λ to loss terms in targeting.py**

In `score_target`, every term that represents a *loss* (sun-collision risk, capture-failure probability, fleet destruction by collision) gets multiplied by `cfg.loss_aversion_lambda`. Gain terms are unchanged.

- [ ] **Step 3:** Run all tests + 10-seed tournament. Save to `results_phase10_loss_aversion.md`.

---

## Phase 10: Validate Fix #4

Gate: ≥ 80% win rate over 10 seeds (final acceptance).

If reach 80%: proceed to Phase 11.
If 75-79%: ship anyway, document the gap, plan v1.2 work.
If < 75%: revert Fix #4; investigate; surface to user.

---

## Phase 11: Final acceptance test + repack

### Task 11.1: Extended tournament (variance reduction)

- [ ] **Step 1: Run 20-seed tournament vs `random`**

Use seeds 0-19, with `random.seed(42)` set globally for opponent determinism.
Save: `docs/iteration_logs/v1.1/final_acceptance.md`.

- [ ] **Step 2: 10-seed tournament vs original sniper**

Confirm we beat the bovard sniper baseline ≥ 60%.

- [ ] **Step 3: 10-seed self-play check**

Run 10 episodes of `[main.agent, main.agent]` (the v1.1 vs itself). Should produce roughly 50/50 — sanity check that the agent isn't deterministically losing to itself due to symmetry quirks.

### Task 11.2: Re-pack and verify G4

- [ ] **Step 1:** `uv run orbit-play pack` — produces submission.tar.gz with new SHA.
- [ ] **Step 2:** G4 smoke test — extract tarball into /tmp/, run a full episode.
- [ ] **Step 3:** Document new SHA in `docs/iteration_logs/v1.1/final_acceptance.md`.

### Task 11.3: Hand-off to user

- [ ] **Step 1:** Surface results: win rate vs random, vs sniper, vs self; new SHA; suggest commit boundary.
- [ ] **Step 2:** Wait for user direction (submit or further iterate).

---

## Risks & mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | Diagnostic target-inference is wrong (cosine > 0.95 mis-attributes) | Fall back: refactor `_decide` to return tagged moves with explicit target_id; ~30 min refactor |
| 2 | Fix #1 causes 0 launches (intercept rejects all moving targets) | Phase 4 gate catches this; revert and try Path 3.B |
| 3 | Multi-tier scoring overflows or has tied scores everywhere | Use `1e6` not `math.inf`; add `+ epsilon * deterministic_tiebreak(planet_id)` to break ties |
| 4 | Hungarian regresses because per-source-best gets stolen by another source | Normalize scores per-source before assigning OR add a "no worse than greedy" floor |
| 5 | 10-seed sample size too small for win-rate gate | Acceptable risk for early phases; Phase 11 uses 20 seeds for the final gate |
| 6 | Org token limit hits mid-iteration | Plan is resumable: each phase has explicit gates and checkpoints, so we can pick up at any phase boundary in a future session |
| 7 | `random.seed(42)` doesn't make random_agent fully deterministic | Document if so; switch to a custom deterministic-random opponent if needed |
| 8 | We hit 80% vs random but lose to sniper | Acceptable for v1.1 ship; v1.2 work item to handle smarter opponents |
| 9 | Fix #4 (λ=1.5) breaks because loss-aversion is too aggressive | Sweep λ ∈ {1.2, 1.5, 2.0} in Phase 10 if 1.5 doesn't pass |

---

## Self-review

**1. Spec coverage:** every Tier A recommendation from `research_findings.md` §"Concrete actionable recommendations" gets a phase: A.2 → Phase 3.A; A.1 → Phase 3.B / 5; A.3 → Phase 7; A.4 → Phase 9. Tier B/C/D items are deferred to v1.2 explicitly.

**2. Placeholder scan:** no "TBD" anywhere; every code block is concrete; every gate has a numerical threshold; every file path is absolute or repo-relative.

**3. Type consistency:** `LaunchPlan` (assignment.py) has `src_id, target_id, angle, ships` matching `[planet_id, angle, ships]` action format. `LaunchRecord` (diagnostic.py) is internal; doesn't need to match anything else. `score_target` signature uses `view, world, config` matching existing call sites.

**4. Gate criteria are objective:** all gates are win-rate thresholds over a specified number of seeds; no hand-wavy "looks good".

**5. Reversibility:** every change is to a single file or a small set; revert via `git checkout HEAD -- <files>`; user owns commits so reverts are non-destructive.

Issue found: I claim "all 37 unit tests still pass" as a goal, but Phase 7 adds a new test for `assignment.py`, so Phase 8+ should expect 38 tests. Already noted in Phase 7 Step 4. ✓

---

## Approval gate

**Before executing this plan**, surface to user:

> "Iteration plan written and saved to `docs/superpowers/plans/2026-04-30-heuristic-v1.1-iteration.md`.
> Phased execution with explicit win-rate gates between each fix. Phase 0-2 build a diagnostic harness and identify the dominant failure mode empirically — only then do we apply targeted fixes.
> Approve to proceed with Phase 0?"

If approved: invoke `superpowers:executing-plans` and execute task-by-task.
If revisions requested: edit inline.
