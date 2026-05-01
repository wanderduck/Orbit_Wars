# Phase 2 Implementation — Design Spec

**Date:** 2026-05-01
**Phase:** 2 (acting on Phase 1 research findings)
**Status:** Awaiting user review before execution
**Predecessors:**
- `docs/superpowers/specs/2026-05-01-competition-codebases-research-design.md` (Phase 1 spec)
- `docs/research_documents/competition_codebases/synthesis.md` (Phase 1 synthesis + red-team review)

## Goal

Execute a focused, time-bounded implementation pass on top of v1.5G that turns 4 of the highest-evidence Phase 1 candidate techniques into testable changes, with disciplined A/B mechanics so we can attribute ladder Δ per technique and exit Phase 2 with reduced uncertainty about which directions are worth pursuing in Phase 3.

Phase 2 is **not** about reaching top-10. The Phase 1 synthesis explicitly states that path is not present in any of the 6 peer notebooks we researched. Phase 2 is about converting research-derived hypotheses into measured ladder evidence so that Phase 3 (or beyond) can proceed from a stronger empirical foundation.

## Note on changed evidence footing (added post-design)

The Phase 1 synthesis quoted a v1.5G baseline of ~600-655 μ (per CLAUDE.md at the time). Post-synthesis the user clarified that v1.5G's latest ladder reading is **~800 μ**, ~100 points above the two prior submissions. This shifts our position in the research cohort from middle-of-pack to upper-middle (only fedorbaart at 850.9 is clearly above us, and we don't have access to their actual agent — only their visualizer notebook).

**Implications for Phase 2 priors per technique:**

- **Step 1 (sparring partner):** *value increased*. mdmahfuzsumon (796.8) and us (~800) being roughly equal makes them a sharper local A/B discriminator than they would be at a wider gap.
- **Step 2 (map-control bonus):** *value reduced*. Source author is now at parity, not above us; "borrowed from a winning peer" framing no longer applies. Still cheap enough to measure under the success criterion.
- **Step 3a (path-collision instrumentation):** *value unchanged or increased*. The "simpler path-clearance correlates with higher score" finding is now weaker (mdmahfuzsumon 796.8 vs us ~800 = noise-band difference), but the instrumentation itself is still worth doing for its own sake. **Bar for triggering 3b raises substantially** — without much more compelling data than the original n=3 finding suggested, do not weaken `path_collision_predicted`.
- **Step 4 (multi-source pincer):** *value modestly reduced*. Sources (mdmahfuzsumon and johnjanson) are now at-or-below us. Still addresses an explicit CLAUDE.md-flagged gap which is independent justification.

**Implication for Δ thresholds:** the ~100 μ submission-to-submission swing observed for v1.5G is much larger than the original ±15 μ thresholds. Thresholds were recalibrated to **±35 μ with min 7 subs OR 5 days per technique** (option E in the A/B Mechanics section below) to better match observed noise without doubling Phase 2 wall-clock.

## Inputs

- Current agent baseline: v1.5G (greedy offense + defense, latest ladder reading ~800 μ, working baseline; ~100 μ swing across recent submissions, treat as not-yet-settled).
- Phase 1 synthesis with red-team review: `docs/research_documents/competition_codebases/synthesis.md`.
- Six Phase 1 briefs in the same directory.
- `mdmahfuzsumon-how-my-ai-wins-space-wars.ipynb` available at `_research_workspace/notebooks/` (gitignored research workspace).
- Project context: `CLAUDE.md` (especially the "Known gaps / be critical" and "Diagnostics & debugging" sections).
- Submission slot budget: ~3/day, ~7 weeks to deadline (2026-06-23).

## Deliverables

1. **Step 1:** New file `src/orbit_wars/opponents/peer_mdmahfuzsumon.py` — a frozen snapshot of mdmahfuzsumon's submitted agent extracted from their notebook, registered in the Typer ladder command alongside existing opponents. NOTICE entry citing source URL + author.
2. **Step 2:** `map_control_bonus: bool = True` flag on `HeuristicConfig` plus the conditional in the target-scoring path. Toggle defaults True post-merge so the active baseline tests the change.
3. **Step 3a:** Local instrumentation of `path_collision_predicted` aborts and (where practical) counterfactual rollouts. Output report at `docs/research_documents/competition_codebases/path_collision_instrumentation.md`.
4. **Step 4:** `multi_source_pincer: bool = True` flag on `HeuristicConfig` plus the no-arrival-sync paired-source launch logic in the offense planner. Defense reserve must be recomputed against both sources' depleted garrisons before launches commit.
5. **Phase 2 wrap-up doc** at `docs/research_documents/phase2_results.md`: per-technique what worked / what didn't / Phase 3 candidate list. Single commit at end of Phase 2.

## Phase 2 ordered plan

| # | Step | Type | Local gate | Ladder cycle |
|---|---|---|---|---|
| 1 | Port mdmahfuzsumon as local sparring partner | Infra (no v1.5G behavior change) | Existing tests pass; opponent runs across 10 quick seeds without crash | None |
| 2 | Map-control bonus toggle | `HeuristicConfig` flag, target-scoring multiplier | Non-regression vs ported mdmahfuzsumon over 100 local seeds, ≤1% win-rate degradation tolerance | Min 7 subs OR 5 days; default revert if Δ < +35 μ |
| 3a | Path-collision instrumentation | Local-only metrics + counterfactual rollouts | None (no behavior change) | None — produces a measurement; if striking, fast-tracks 3b as a hot-fix decision |
| 4 | Multi-source paired pincer (no arrival sync, mdmahfuzsumon-style) | `HeuristicConfig` flag, offense-planner change | Non-regression vs ported mdmahfuzsumon over 100 local seeds | Min 7 subs OR 5 days; default revert if Δ < +35 μ |

Sequential execution. Single-developer workflow doesn't gain from parallel branches.

## Per-technique sketches

### Step 1 — Sparring partner port

Pull source from `_research_workspace/notebooks/how-my-ai-wins-space-wars.ipynb` (cell containing the `%%writefile submission.py` block). Extract verbatim into `src/orbit_wars/opponents/peer_mdmahfuzsumon.py`. Treat as a frozen third-party snapshot — **no edits to the agent code itself**. Add a header comment block citing source URL, author handle, ladder rank/score at time of port (rank 498, score 796.8 as of 2026-05-01 leaderboard download), and the licensing position (public Kaggle notebook, attribution preserved).

Register in the Typer ladder command at `src/tools/cli.py` (opponent registry around line 75) alongside `competent_sniper`, `aggressive_swarm`, `defensive_turtle`; expose via `src/orbit_wars/opponents/__init__.py` if needed. Verify it runs across 10 quick seeds without raising. Verify it produces actions our env accepts (no validation errors). Add a smoke test ensuring the agent imports and returns a list on a sample obs.

Estimated wall-clock: half a day to one day.

### Step 2 — Map-control bonus

Add `map_control_bonus: bool = True` to `HeuristicConfig` (defined at `src/orbit_wars/heuristic/config.py`; default True so post-merge baseline runs the change). In the offense target-scoring path within `src/orbit_wars/heuristic/strategy.py`, when the flag is True multiply target value by 1.4 if `dist(planet.position, CENTER) <= 20`, by 1.2 if `<= 35`, by 1.0 otherwise. Constants chosen to match mdmahfuzsumon's source verbatim — no tuning in Phase 2.

Local A/B vs ported mdmahfuzsumon: run 100 seeds with `map_control_bonus=True` vs 100 seeds with `map_control_bonus=False`; require non-regression (≤1% win-rate degradation tolerance to absorb noise floor). If pass, merge to master, submit to ladder, run cadence.

Estimated wall-clock: ~1 hour for the change, half a day for local test, then ladder cadence (4 days).

### Step 3a — Path-collision instrumentation

Add per-game counters in `WorldModel` and the launch path:
- Total `path_collision_predicted` aborts per game.
- Per-abort log of `(turn, source_id, target_id, abort_reason)`.

If practical (decide based on complexity at implementation time): for each abort, run a counterfactual rollout that forces the launch through anyway and check whether the fleet would have actually been intercepted by the predicted-colliding planet. Output rates: aborts per game, false-positive rate (predicted collision but no actual collision in counterfactual).

Run 50-100 local self-play seeds. Output a markdown report at `docs/research_documents/competition_codebases/path_collision_instrumentation.md` with: total aborts, abort rate per game, false-positive rate (if counterfactual runs), example aborts (ones with high false-positive risk).

**No behavior change in 3a.** Decision tree on results:
- If aborts are rare AND false-positive rate is low: path-collision is doing its job; close the loop, no 3b needed.
- If aborts are frequent AND false-positive rate is high: 3a data justifies a 3b hot-fix proposal — add a `relax_path_collision: bool = True` toggle that disables (or weakens) the check, ladder-test as a normal Phase 2 technique with the standard cadence. Decision to invoke 3b is made by the user once 3a data is presented.
- Anything ambiguous: defer to Phase 3 with the data attached.

Estimated wall-clock: half a day to one day for instrumentation + report.

### Step 4 — Multi-source paired pincer

Add `multi_source_pincer: bool = True` to `HeuristicConfig` at `src/orbit_wars/heuristic/config.py` (default True post-merge). In the offense planner within `src/orbit_wars/heuristic/strategy.py`: when the nearest-source's available ships fall short of `ships_needed` for a target, search owned planets for a partner source whose available ships cover the deficit; commit both fleets the same turn, no arrival-time matching. **Critical interaction:** defense reserve / `find_threats` / `plan_defense` must be recomputed against both sources' depleted garrisons before launches commit — otherwise a successful pincer leaves both sources defenseless to forecast threats.

Implementation sequence inside the planner:
1. Identify candidate targets where nearest-source falls short.
2. For each candidate, search a partner source whose available ships cover the deficit (after defense reserve).
3. Tentatively commit both launches in the planning ledger.
4. Re-run defense planning against the post-launch garrison state.
5. If defense planning now flags either source as under-defended, abort the pincer; fall back to single-source greedy.
6. Otherwise, commit both launches.

Local A/B vs ported mdmahfuzsumon: 100 seeds with toggle on vs off; non-regression gate. If pass, ladder cycle as standard.

Estimated wall-clock: 1-2 days for the change (more invasive than #2), half a day for local test, then ladder cadence.

## Branch / git workflow

One feature branch per step, off `master`:
- `phase2/01-sparring-partner-mdmahfuzsumon`
- `phase2/02-map-control-bonus`
- `phase2/03a-path-collision-instrumentation`
- `phase2/04-multi-source-pincer`

Per-technique flow for #2 and #4 (the gated, ladder-tested techniques):
1. Create branch.
2. Implement; toggle defaults **True** in `HeuristicConfig`.
3. Local A/B vs ported mdmahfuzsumon: 100 seeds, technique-on vs technique-off, ≤1% win-rate degradation tolerance.
4. If pass: merge to `master`, submit to ladder, begin cadence.
5. After cadence completes (min 7 subs OR 5 days, whichever lands first):
   - Δ < -35 μ: defensive auto-revert (revert commit, no approval gate, report after).
   - -35 ≤ Δ < +35 μ: I report data, default recommendation revert; user can override to keep.
   - Δ ≥ +35 μ: default-keep adopted; user can override.
6. Branch deleted post-merge whether kept or reverted.

Steps 1 and 3a have no ladder phase and no auto-revert — they merge cleanly once tests pass and the deliverable (working opponent / instrumentation report) is in place.

## A/B mechanics

- **Local non-regression gate:** 100 self-play seeds at fixed `random.seed(42)` (per CLAUDE.md note: seed once before the loop, not per-seed). Win-rate computed as fraction of episodes where our agent's reward > opponent's reward at termination. Tolerance ≤1% degradation to absorb noise floor.
- **Ladder cadence:** start clock at first submission. Min 6 subs OR 4 days, whichever lands first. We submit once per available slot (typically up to 3/day) until we hit the minimum, then continue at our normal rate until the day-bound triggers if needed.
- **Adopt/revert decision rule** *(thresholds calibrated post-baseline-update — option E selected)*:
  - Δ < -35 μ → defensive auto-revert (no approval gate).
  - -35 ≤ Δ < +35 μ → I report data with a default recommendation of **revert** (Phase 2 success criterion is uncertainty reduction; carrying ambiguous changes forward dilutes Phase 3 attribution). User can override to keep.
  - Δ ≥ +35 μ → default-keep adopted; user can override to revert.
  - Cadence: min 7 subs OR 5 days, whichever lands first.

  *Calibration rationale: the observed ~100 μ swing across recent v1.5G submissions implies the noise floor at our submission count is wide. Original spec set X = 15 μ which would have put almost all outcomes in the ambiguous band. ±35 μ is the user's calibrated middle ground — tighter than the observed swing but loose enough to leave room for real signal.*
- **Hard-regression hot revert:** if at any point during the cadence Δ < -70 μ after at least 3 subs, I auto-revert immediately even before formal cadence completes. (Roughly 2× the band, well beyond plausible noise. Signal is unambiguous; waiting wastes slots.)
- **Baseline anchoring:** v1.5G (current `master` head before Phase 2 work) is the persistent baseline reference. Δ is measured relative to v1.5G's most recent stable score (not to whichever variant most recently shipped). If v1.5G itself drifts on the ladder during Phase 2 (sample variance), I'll flag and we recalibrate.

## Decision authority

- **Local gate failure:** hard rule, automatic — don't ship; fix or abandon. I report the failure mode and propose next steps (fix the bug, scrap the technique, or revisit the gate threshold).
- **Ladder hard regression (Δ < -35 μ):** defensive auto-revert. No approval gate. Report after.
- **Ladder ambiguous (-35 ≤ Δ < +35 μ):** I report data with a default recommendation of **revert** (per Phase 2 uncertainty-reduction goal). User can override to keep.
- **Ladder positive (Δ ≥ +35 μ):** default-keep, user can override.
- **3b fast-track (conditional on 3a data):** I propose a 3b plan if 3a's data is striking; user decides whether to insert as a hot-fix in Phase 2 or defer to Phase 3.
- **Mid-Phase-2 reordering:** if a step earlier in the queue produces results that change priorities (e.g., map-control regresses hard, suggesting our scoring function is more fragile than expected), I flag and propose a reorder; user decides whether to deviate from the spec.

## Reporting cadence

- After each step completes its full cycle (4 reports total, plus the Phase 2 wrap).
- Immediately on any blocker: third-party agent doesn't run, sandbox issues, lint/test failures we can't resolve in <1 hour, ambiguous local-gate result.
- Immediately on hard ladder regression — even before formal cadence completes if Δ < -30 μ after ≥3 subs.
- Phase 2 wrap-up doc at `docs/research_documents/phase2_results.md`: per-technique what worked, what didn't, Phase 3 candidate list. Single commit.

## Constraints

- No edits to the third-party agent code (mdmahfuzsumon's `submission.py`) — frozen snapshot only.
- All toggles default **True** post-merge so the active baseline runs the change being tested.
- Local non-regression gate uses `random.seed(42)` once before the seed loop, per CLAUDE.md.
- All commits attributed to project commit style (short imperative subject; existing convention from CLAUDE.md / git log).
- No skipping pre-commit hooks unless explicitly authorized by user.
- Pulled `.ipynb` files in `_research_workspace/` remain gitignored; only the extracted `submission.py` source goes into `src/orbit_wars/opponents/peer_mdmahfuzsumon.py` with attribution.
- No changes to submission packaging (`tools.cli pack`), Kaggle CLI interaction, or env adapters — orthogonal to Phase 2 scope.

## Out of scope

- Any technique not in the 4-step plan: vulnerability-window scoring, sun-tangent bypass, crash-exploit, eco-mode tiering, planet triage, speed-optimal over-commit, three-source swarm, inferred enemy destinations, opponent-aggression defense scaling. **All deferred to Phase 3** or scrapped based on Phase 2 results.
- Multi-source coordination beyond the simple no-sync pincer (no arrival-time matching, no 3-source swarm).
- Step 3b (path-collision relaxation) without 3a's data backing it.
- Ladder-testing techniques without the local non-regression gate.
- Tuning mdmahfuzsumon's constants (1.4, 1.2, 20, 35, etc.) — verbatim only in Phase 2; tuning is a Phase 3 question.
- Cleanup / refactoring beyond what each technique strictly requires.
- Phase 3 planning during Phase 2 execution (planning happens at Phase 2 wrap).
- The C-style "improvement gate" (require ≥5% local improvement to ship) — held in reserve as a possible Phase 2.5 if ladder results are noisy enough that non-regression isn't a strong enough discriminator.
- The D-style parallel codebase (`src/main_v2.py`) — held in reserve if some technique turns out too entangled for a simple flag toggle.
- Any Kaggle-CLI submission automation beyond what already exists in the project.

## Done state

All 4 steps have completed their cycle:
- Step 1: ported sparring partner merged to master, smoke-tested, registered in ladder.
- Step 2: map-control bonus has either been adopted (default True kept) or reverted (default False or commit reverted) based on ladder data; result documented.
- Step 3a: instrumentation report written and committed; 3b decision (fast-track / defer / kill) made.
- Step 4: multi-source pincer has either been adopted or reverted based on ladder data; result documented.
- Phase 2 wrap-up doc committed at `docs/research_documents/phase2_results.md` with per-technique results and Phase 3 candidate list.
