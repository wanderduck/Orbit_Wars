# Phase 2 Results — Wrap-up

**Date:** 2026-05-01 to 2026-05-02
**Spec:** `docs/superpowers/specs/2026-05-01-phase-2-implementation-design.md`
**Predecessor research:** `docs/research_documents/competition_codebases/synthesis.md`
**Status:** Phase 2 complete. Phase 3 candidate list at the end.

## Per-step outcomes

| Step | Outcome | Branch | On master? |
|---|---|---|---|
| 1. Sparring partner port (mdmahfuzsumon) | ✅ Shipped | `phase2/01-sparring-partner-mdmahfuzsumon` | YES (merged at `8cbbfce`) |
| 2. Map-control bonus | ❌ Failed local A/B (-3%) | `phase2/02-map-control-bonus` | NO (unmerged) |
| 3a. Path-collision instrumentation | ✅ Shipped (0.3% FP rate) | `phase2/03a-path-collision-instrumentation` | YES (merged at `7e04df1`) |
| 4. Multi-source pincer + 2 fleet-sizing toggles | ❌ Bundle abandoned | `phase2/04-pincer-and-fleet-sizing` | NO (unmerged) |

Net change to v1.5G's behavior on master: **only Step 1's sparring partner port** (a non-behavior-changing addition; opponents pool only). The agent itself is unchanged from session start.

## Phase 2 success criterion: MET

The spec defined success as "we know which of the 4 techniques are net-positive, neutral, or net-negative on the ladder; produce a Phase 3 candidate list." We didn't actually ship anything to ladder for Step 2 or Step 4 (both failed local gates), so we don't have ladder Δ data. **But we exit Phase 2 with strong local evidence on each:**

- **Step 1 (sparring partner):** Now exists. Discriminator quality TBD (it's only one peer; vs more diverse opponents would be stronger).
- **Step 2 (map-control bonus):** Local A/B vs `peer_mdmahfuzsumon` = -3% Δ (96% vs 99%). Borrowed from a peer we beat, applied as a sort-key adjustment in greedy. Not net-positive locally.
- **Step 3a (path-collision):** Counterfactual rollout = 0.3% false-positive rate. Check is doing real work; do NOT weaken it.
- **Step 4 (bundle of inbound + speed-optimal + pincer):**
  - Original 2-variant gate said "passes" (98% vs 98% Δ=0). This was misleading.
  - Inverse ablation (1 toggle ON, others OFF) revealed each individual contribution: inbound = 0%, speed = 0%, pincer = **-5% standalone**.
  - Investigation of pincer found the failure mode: ~8 long-range commits per game with ETA 27-40 turns, tying up ~40 ships in transit for half the game.
  - Fix attempt (pincer ETA cap) tested 4 cap values (10/15/20/no_cap); none beat control. Pincer is dead-on-arrival vs this opponent regardless of cap.
  - Other two toggles produced **identical** outcomes to control on every seed (same 3 lost games), suggesting they're either behaviorally inert or change behavior in ways `peer_mdmahfuzsumon` doesn't differentiate.

**Phase 2 didn't yield a ladder gain, but it did reduce uncertainty significantly.** We now have empirical evidence about 4 candidate techniques rather than just synthesis-based hypotheses.

## Lessons learned (methodology)

These are the most valuable takeaways from Phase 2 — they should shape every future Phase 3 experiment:

### 1. The orbit_wars env consumes Python's global random state

CLAUDE.md mentions this in passing (per the random_agent / env-internals note). Step 4 made it concrete: same config + same env seed produces **different game outcomes** depending on what position-in-stream the game is at. The original Step 4 A/B's "98% vs 98% gate passed" wasn't wrong about the per-script data, but cross-script comparison of "ON 98%" vs "ablation baseline 93%" was fundamentally invalid.

**Implication:** any comparison across separately-launched A/B scripts is invalid. To compare configs, run them in the same script with matched random-stream positions (alternating per seed). This is now documented in CLAUDE.md.

### 2. 2-variant gates can be misleading

Step 4 passed its 2-variant gate (ON vs OFF, both 98%). The 4-variant ablation revealed pincer was -5% standalone. **A 2-variant comparison can hide a problematic toggle if the two variants happen to be equally bad in different ways.** Multi-variant ablations are far more informative when investigating a bundle.

### 3. Local opponent saturation limits A/B usefulness

`peer_mdmahfuzsumon` is the only local opponent at-or-near our skill level, and v1.5G dominates it 97-99% in most configs. That ceiling means small-effect changes are invisible against this opponent — we'd need either a much harder local opponent (top-10 agents don't share code) or much larger sample sizes per A/B to detect ladder-relevant effects locally. **This is the structural bottleneck for any future single-technique A/B testing.**

### 4. Ladder noise is wide

CLAUDE.md was updated this session with v1.5G readings spanning 650-800 μ across submissions (~100 μ swing). This makes per-technique ladder testing expensive: detecting a +30 μ improvement at reasonable confidence requires ~12-15 samples = ~4-5 days of slot budget. **Bundling techniques into a single ladder test loses attribution but amplifies signal** — worth considering when slots are scarce.

## Final Phase 3 candidate list (updated)

Reordered based on what we learned in Phase 2. Items ranked by signal-strength × cost × independence-from-the-bottlenecks-we-just-discovered.

1. **CMA-ES tuning framework over `HeuristicConfig`** (was synthesis recommendation #1; now even more clearly the highest-leverage). Builds an automated mechanism that varies many config values at once and measures aggregate fitness across multiple opponents in parallel. **Solves the local-opponent-saturation problem** by testing against the full local pool simultaneously instead of one peer at a time. Modal credit ($60) covers the parallel compute. ~1 week of infrastructure dev. Pays back across every subsequent tuning decision. *This is the next workstream.*
2. **Add more-diverse local opponents.** The bottleneck for any non-CMA-ES A/B is having only one near-skill peer. If we vendor a second peer (johnjanson is the next obvious candidate at 747.8 μ on the LB) we get a 2-opponent local pool. ~half-day dev.
3. **Investigate the inert-toggle question** with proper instrumentation. Toggles 1 and 2 from Step 4 produced identical outcomes to control. Either they're truly behaviorally inert (and removing them costs nothing) or they're changing behavior in ways the local opponent doesn't differentiate (in which case ladder might surface a real signal). Adding fire-rate counters and a few seeds of trace-logging would resolve. ~half-day.
4. **CBA interception** (from `AI_Heuristics_for_Opponent_Analysis.md`). Geometric alternative to our `aim_with_prediction` fixed-point lead-aim. Standalone, A/B-able via a config toggle. ~1 day.
5. **Influence maps** for tactical assessment ("contested? safe? high value?"). 2-3 days. Becomes the integration point for several other Phase 3 ideas.
6. **Lightweight Bayesian opponent modeling** (mdmahfuzsumon's `compute_enemy_aggression` formalized + extended). Per-opponent aggression tracking → dynamic defense scaling. ~1-2 days.

Items intentionally NOT in the priority list (Phase 1/2 work that didn't pan out):
- Map-control bonus (failed Step 2 A/B; could re-test under CMA-ES with different constants but not standalone).
- Multi-source pincer (failed Step 4 investigation; mdmahfuzsumon's source uses it but we couldn't reproduce its value vs the same author's agent).
- Speed-optimal-send and inbound-enemy tracking as standalone changes (locally inert; could re-test under CMA-ES bundled with other changes).
- Crash-exploit, vulnerability-window scoring, sun-tangent bypass, three-source swarm — all from synthesis ranks 7-10. Lower confidence; should wait for CMA-ES infrastructure before attempting individually.

## Branch state at end of Phase 2

- `master` — production. v1.5G + ported sparring partner (Step 1) + path-collision instrumentation tooling (Step 3a). All other Phase 2 changes NOT merged.
- `phase2/01-sparring-partner-mdmahfuzsumon` — merged, can be deleted.
- `phase2/02-map-control-bonus` — unmerged (failed local A/B). Preserved for posterity / possible CMA-ES re-test.
- `phase2/03a-path-collision-instrumentation` — merged, can be deleted.
- `phase2/04-pincer-and-fleet-sizing` — unmerged (abandoned). Preserved for posterity / possible CMA-ES re-test of inbound + speed toggles.

Three commits on master ahead of `origin/master` were not pushed during Phase 2 (research-only, kept local). Pushing is the user's call.

## Pending: Phase 3 starts with CMA-ES framework

Per the agreed direction at end of Phase 2: pivot to building the tuning framework before any further single-technique experiments. This deserves its own brainstorm + spec — see next session.
