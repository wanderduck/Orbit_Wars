# Phase 2 Step 4 — Status Snapshot (2026-05-01, late)

**Read this cold to resume Step 4 work.** Written after the inverse ablation
landed while you were asleep. No code changes were committed in your absence;
nothing was shipped to the ladder.

## Headline

**The bundle should not ship as-is. The `multi_source_pincer_enabled` toggle is the
problem; the other two are locally neutral.**

## Inverse ablation result (the definitive local data)

100 self-play seeds vs `peer_mdmahfuzsumon`, each variant has only ONE toggle ON
with the other two OFF. Within-script comparison (cross-script invalid due to
the env's hidden random-state consumption — see Methodology Caveat below).

| Variant | Toggles ON | W-L | Winrate | Δ vs control |
|---|---|---|---|---|
| all_off (control) | none | 97-3 | 97% | 0.0% |
| only_inbound | account_for_inbound_enemy | 97-3 | 97% | 0.0% |
| only_speed | speed_optimal_send | 97-3 | 97% | 0.0% |
| only_pincer | multi_source_pincer | 92-8 | 92% | **-5.0%** |

`only_inbound` and `only_speed` produce **identical** outcomes to the control —
literally the same 3 lost seeds. So in isolation against this opponent, neither
toggle changes the agent's behavior detectably (or it changes behavior in ways
that don't shift game outcomes).

`only_pincer` clearly hurts: 5 additional losses, no compensating wins.

This explains the original "bundle" ablation result (93% baseline / 96-98% when
each toggle removed): the pincer was the active drag, the other two were just
neutral riders. Removing the pincer from the bundle (minus_pincer = 98%) was
~equivalent to all_off (97%).

## Why pincer probably hurts

A few hypotheses worth investigating before any further pincer-related work:

1. **Over-commits at the wrong time.** Pincer launches both `primary` (full
   available ships) AND `partner` (deficit). If the planet has even 1 enemy
   fleet inbound that we miscounted, both sources arrive depleted and we lose
   the target AND have weakened sources for the next turn. The local games
   probably don't punish this against `peer_mdmahfuzsumon` heavily, so the
   -5% may understate the real damage.
2. **Partner search picks distant partners.** The current implementation in
   `_plan_pincer_pass` (strategy.py) sorts `available_sources` by distance to
   the target, picks `sorted_srcs[0]` as primary, then iterates `sorted_srcs[1:]`
   for any partner that covers the deficit. The partner can be very far, sending
   slow ships that arrive much later than primary. Combat at the target might
   resolve before partner arrives.
3. **No defense recomputation after pincer commits.** The Step 4 spec
   explicitly flagged this: "defense reserve must be recomputed against both
   sources' depleted garrisons before launches commit." We rely on `available`
   already accounting for defense reserves, but committing two sources
   simultaneously was not defense-rechecked. Could expose forecast threats.
4. **Greedy didn't already cover this.** If the greedy main pass left an
   enemy target unattacked, it's because no single source could cover it. The
   pincer fallback is for exactly these cases — but if no single source can
   cover, the target may genuinely be too well-defended; throwing two sources
   at it loses more than abstaining.

## What `account_for_inbound_enemy` and `speed_optimal_send` actually did

Identical outcomes to control on every seed. Two interpretations:

a) **They had zero behavioral effect.** Possible if (e.g.) inbound enemy
   forecasts at contested neutrals never extended `eval_turn` differently from
   the existing logic, or if `speed_optimal_send` never found cases where
   over-commit shaved a turn off ETA. Worth instrumenting — count how often
   each toggle's branch was actually taken across the 100 games.
b) **They changed behavior but the changes didn't matter against this opponent.**
   Possible if the changes are real but `peer_mdmahfuzsumon` doesn't punish or
   reward them. Ladder behavior could differ.

Without further instrumentation we can't tell which. Cheap option: add log
counters to each toggle's branch and re-run a few seeds.

## Methodology caveat (important)

CLAUDE.md notes that the orbit_wars env consumes Python's global random state
("env internals consume Python's global random state"). This means the same
config/seed combination will produce DIFFERENT outcomes depending on what
position it occupies in the game stream.

Concretely:
- The original Step 4 A/B (`/tmp/phase2_step4_ab.py`) ran each seed with 2
  variants (ON, OFF). It got ON=98%, OFF=98%.
- The bundle ablation ran each seed with 4 variants. Got baseline=93%.
- The inverse ablation also runs each seed with 4 variants. Got control=97%.

These winrates are NOT directly comparable across scripts — even with identical
configs, position-in-stream changes the env's random outcomes. **Within-script
comparisons remain valid** (same script structure → same random consumption
pattern → fair A/B between variants).

The original A/B's "98% vs 98% gate passed" was therefore misleading: it didn't
prove the bundle was harmless, it just compared two configs in matched random
positions. The inverse ablation is the more trustworthy test because all 4
variants face matched random positions within the same loop.

## Branch state (verified before sleep)

- `master`: clean. HEAD = `3faa0dd` (docs: Step 4 expansion addendum).
- `phase2/04-pincer-and-fleet-sizing`: HEAD = `7349ba2` (Step 4 implementation).
  Has all 3 toggles, no map_control_bonus. **Currently checked out.**
- `phase2/02-map-control-bonus`: unmerged (failed Step 2 A/B).
- `phase2/01-sparring-partner-mdmahfuzsumon`: already merged to master.

Nothing was shipped to the Kaggle ladder during this session.

## Three options for resume

### A) Reduce the bundle: drop pincer, ship the other two

Set `multi_source_pincer_enabled` default to False on the branch. Keep
`account_for_inbound_enemy_enabled` and `speed_optimal_send_enabled` at True.
Local A/B'd this 2-toggle subset is at worst neutral. Ship to ladder.

Risk: if the two remaining toggles are truly behaviorally inert (interpretation
(a) above), ladder result will be ~zero Δ — wasted slots. If they're behaviorally
real (interpretation (b)), ladder might show signal.

Cost: ~12 ladder slots (~4 days at our 3/day rate) under the recalibrated
±50 μ thresholds.

### B) Investigate before any ladder

Add instrumentation to count how often each toggle's branch fires (similar to
Step 3a's path_collision_predicted instrumentation). Run a few seeds. If the
toggles fire frequently but don't change outcomes, they're neutral by accident
of opponent behavior — worth keeping for ladder. If they barely fire at all,
the implementation has a bug or the conditions never trigger — worth fixing or
removing.

Then also investigate WHY pincer hurts (the 4 hypotheses above are all worth
checking). Could be a 1-line fix (e.g., add defense recomputation, restrict
partner search to nearby planets).

Cost: ~half-day to a full day of dev. Higher confidence in whatever ships.

### C) Abandon Step 4 entirely

Document the negative result in the Phase 2 wrap-up doc. Move on to other
Phase 3 candidates (CBA interception, influence maps, lightweight Bayesian
opponent modeling). The synthesis Phase 3 outlook section listed these.

Cost: zero compute, but loses the Step 4 work entirely.

## My recommendation

**B, then probably A with pincer fixed if investigation finds it's a clear bug.**
The "pincer is buggy" hypothesis is the most likely explanation for the -5%,
and Step 4 was conceptually motivated by your replay observations. Throwing
out the work without investigating feels like under-using the data we already
have. ~Half a day of investigation could turn a 2/3 negative result into a
3/3 positive one.

But A (ship the 2 working toggles) is fine if you'd rather move on. The two
neutral toggles are reversible if ladder shows regression.

C is the most defensive option. Reserve for the case where investigation in
B reveals all three toggles are conceptually broken, not just buggy.

## Quick references

- **Inverse ablation raw data:** `/tmp/phase2_step4_inverse_ablation_result.json`
- **Bundle ablation raw data:** `/tmp/phase2_step4_ablation_result.json`
- **Original Step 4 A/B:** `/tmp/phase2_step4_ab_result.json`
- **Branch with implementation:** `phase2/04-pincer-and-fleet-sizing` (HEAD `7349ba2`)
- **Spec addendum (already on master):** `docs/superpowers/specs/2026-05-01-phase-2-implementation-design.md` §"Step 4 expansion (added 2026-05-01 evening)"
- **Implementation files:**
  - `src/orbit_wars/heuristic/config.py` lines ~73-101 (the three toggles)
  - `src/orbit_wars/heuristic/strategy.py` `_try_launch` (toggles 1+2 wired in),
    `_plan_offense_greedy` + `_plan_pincer_pass` (toggle 3)
