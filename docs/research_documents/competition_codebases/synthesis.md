# Competition Codebases — Synthesis

**Date:** 2026-05-01
**Phase:** 1 (research only, no implementation)
**Sources:** 6 per-codebase briefs in this directory
**Author ladder context:** all 6 authors verified against `_research_workspace/leaderboard.csv` (downloaded 2026-05-01 09:44 UTC). Ranks 318-988, scores 616.4-850.9. Top of LB is 1623.1 (Shun_PI). Our v1.5G sits at ~600-655 μ — *middle of this peer cohort, not behind it*. **(See Baseline updates below — the original number underestimated the noise band; v1.5G is high-variance with submissions spanning ~650-800 μ. Working median is ~700 μ.)**

## Baseline update #1 — 2026-05-01 (mid-day)

After the synthesis above was committed, the user clarified that **v1.5G's latest ladder reading was hovering just under 800 μ — approximately 100 points above the two prior submissions** (which were v1.5-Hungarian variants). Treated the new ~800 baseline as a working number, not a settled truth: the ~100 μ swing across submissions was flagged as at the edge of plausible ladder noise.

**Implications taken at the time:**

- mdmahfuzsumon (796.8) interpreted as roughly at parity with us, not above us. Three of the top-5 ranked techniques (#1 pincer, #2 map-control, #3 aggression scaling) source from mdmahfuzsumon — the red-team's concern #3 (n=1 selection bias) was sharpened.
- The "simpler path-clearance correlates with higher score" finding (TL;DR #2) was weakened: at the assumed ~800 baseline, the spread mdmahfuzsumon 796.8 vs us ~800 was inside ladder noise.
- fedorbaart at 850.9 was framed as the only clearly-above-us peer.

## Baseline update #2 — 2026-05-01 (later) — supersedes #1

The user reported v1.5G subsequently **drifted back down to just below 700 μ** with new submissions. This confirms what update #1 already flagged as risk: the ~800 reading was inside the variance band, not a stable improvement. Working baseline is now better described as **"~700 μ median with ~100 μ noise per submission"** — submissions can land anywhere in roughly 650-800.

**Corrected implications (this section supersedes update #1):**

- **mdmahfuzsumon (796.8) is back to being above us.** The original TL;DR #1 framing ("ships at 796.8 μ — above our 655") was correct; the brief mid-day "at parity" interpretation was based on a high-noise ladder reading and is hereby walked back.
- The red-team's concern #3 (n=1 selection bias on the only above-us peer) **stands as originally framed** — three of the top-5 ranked techniques source from mdmahfuzsumon, and they ARE above us, but n is still 1.
- The "simpler path-clearance correlates with higher score" finding (TL;DR #2) is **back in play but still weak** — n=3 with confounders, per the red-team's original critique. Step 3a instrumentation results (when they land) will inform whether to act on it.
- fedorbaart at 850.9 remains the highest-scoring author in the research set; mdmahfuzsumon and johnjanson are now both above us again.

**What still does NOT change:**

- mdmahfuzsumon as sparring partner remains valuable — having an above-us peer in the local pool is exactly the discriminator we wanted.
- Phase 2 success criterion (uncertainty reduction across 4 techniques) is unchanged.
- The 4 Phase 2 candidates remain worth measuring; per-technique cost estimates haven't moved.
- Per-codebase briefs are unchanged (author ladder data was a snapshot at the time of pull).

**Implication for Phase 2 thresholds (±35 μ, 7 subs / 5 days, calibrated under "option E" in the spec):** these may now be too tight. The ~100 μ submission-to-submission swing means a true +35 μ improvement could easily be masked by noise across 7 submissions. Worth revisiting the threshold calibration before Step 4's eventual ladder phase — likely loosening to ±50-75 μ and/or doubling the sample count.

This addendum is layered on after the original synthesis was committed (commit `ca83317`). The body above is preserved verbatim as the original research deliverable. Update #1 is preserved for honest record-keeping; update #2 supersedes it.

## TL;DR

1. **The strongest cross-codebase pattern is multi-source coordination.** 3 of the 4 functional agents (mdmahfuzsumon, johnjanson, rahulchauhan016) attempt some form of multi-planet attack synchronization; the 4th (omega-v5) lists a "gang-up" mission type whose internals weren't characterized in detail. CLAUDE.md flags multi-source as a v1.5G gap. mdmahfuzsumon's "two-planet pincer with no arrival sync" is the cheapest variant and ships at 796.8 μ — above our 655.
2. **Counter-intuitive finding: simpler path-clearance correlates with higher ladder scores in this peer set.** mdmahfuzsumon (796.8) does only a 3-step source-side sun check; johnjanson (747.8) checks only sun-collision; v1.5G (~655) does full per-turn moving-planet path-collision prediction. Worth instrumenting whether our path-clearance is over-conservative and skipping winning launches.
3. **Cheapest single hint:** mdmahfuzsumon's `map_control_bonus` (target value × 1.4 within 20 of center, × 1.2 within 35). One-line scoring multiplier. Trivial cost, low regression risk, comes from a peer who outscores us.
4. **Most novel idea:** omega-v5's vulnerability-window scoring (track enemy planets that just emitted ≥VULN_MIN_SENT ships totalling ≥VULN_SENT_RATIO of garrison → ~6× target value). No other peer attempts this. Cheap to add; signal quality unproven (omega-v5 is at 616.4).
5. **Inflated marketing is the norm here.** 4 of 6 titles wildly overclaim ("AGI", "TOP 5", "2000.4 target", "Supreme Domination") vs actual ranks 318-988. None of these notebooks contains the formula for top-10. We're harvesting hints, not solutions.

## Cross-codebase patterns (≥2 sources)

### Multi-source coordination
- **mdmahfuzsumon** ([brief](mdmahfuzsumon-how-my-ai-wins-space-wars.md)): paired-source pincer when no single planet can field `needed`; both fleets launch same turn, no arrival-time matching.
- **johnjanson** ([brief](johnjanson-lb-max-score-1000-agi-is-here.md)): three-source swarm with explicit "no two-source subset can solo it" gate.
- **rahulchauhan016** ([brief](rahulchauhan016-orbit-wars-target-score-2000-4.md)): MCTS rollouts implicitly explore multi-source action sets.
- **Evidence-of-effectiveness:** indirect — top-scoring peer in our cohort (mdmahfuzsumon 796.8) uses the simplest version. johnjanson's more elaborate version sits below at 747.8.
- **Significance:** v1.5G is single-source-per-decision. Each owned planet picks a target independently. CLAUDE.md explicitly flags this as a known gap. The cheapest version (mdmahfuzsumon's no-arrival-sync pincer) requires only summing reachable ships across N sources before deciding launch sizes — minimal architectural change.

### Path-clearance is weaker than ours in higher-scoring peers
- **mdmahfuzsumon** (796.8): only checks 3-unit step away from source via `segment_hits_sun`; no full path integration vs moving planets.
- **johnjanson** (747.8): only sun-collision check (`segment_hits_sun`); explicitly violates rule E3 ("fleets collide with ANY planet on path").
- **omega-v5** (616.4): also only sun-collision (no per-turn moving-planet sim).
- **Evidence-of-effectiveness:** counter-intuitive — none of the higher-scoring peers do what v1.5G does (`path_collision_predicted` walks the trajectory turn-by-turn). This is suggestive, not conclusive: confounders include skill gaps, opponent matchmaking, and small sample (3 data points).
- **Significance:** worth empirically measuring how often `path_collision_predicted` aborts launches in real games and whether aborted launches would have actually collided. We may be paying a premium in skipped opportunities for protection against rare events.

### Forecast-defense via per-planet timeline simulation
- **omega-v5**: `simulate_timeline` walks every turn to HORIZON=120, bisects min `keep_needed`.
- **johnjanson**: `simulate_planet_timeline` to a horizon with binary-searched `keep_needed`.
- **v1.5G**: `WorldModel.base_timeline` plus `find_threats` walks for ownership flips.
- **Significance:** we already have this in some form. Both peers' implementations are cleaner formalisations (binary search, explicit horizon). Worth comparing whether our `find_threats` resolution matches theirs.

### Opponent modeling beyond raw garrison
- **mdmahfuzsumon**: opponent-aggression scaling — ratio of in-flight enemy ships vs garrisoned; if >0.5, defense reserves ×1.5.
- **johnjanson**: sliding-window stacked-arrival defense buffer (3-turn window, reserve 0.20 of largest stack).
- **omega-v5**: `detect_rush` projects every enemy fleet velocity vector onto our planets, boosts counter-rush target.
- **Significance:** v1.5G's defense is reactive to forecast individual-planet ownership flips. Multiple peers add a *behavioral* layer (how aggressively is the opponent acting overall?) which is orthogonal. Cheapest to start with mdmahfuzsumon's binary aggressiveness flag.

## Per-technique deep dives (ranked: evidence × fit × low-cost-to-try)

### 1. Multi-source coordination (paired pincer)
- **Source:** mdmahfuzsumon `find_coordinated_sources` (cell 1).
- **Why it might help:** addresses the explicit v1.5G gap; cheapest peer who outscores us uses exactly this.
- **Fit with v1.5G:** offense planner currently iterates owned planets independently. Add a pre-pass: when nearest-source can't field `needed`, search for a partner source whose available ships cover the deficit; commit both same turn.
- **Cost:** moderate (a few hours) — extends offense planner; needs to interact with reserve/defense ledgers correctly.
- **Regression risk:** moderate. Two simultaneous launches from different sources mean both sources' garrisons drop simultaneously; if defense reserve isn't recomputed, weaker source becomes vulnerable.

### 2. Map-control target-value bonus
- **Source:** mdmahfuzsumon `map_control_bonus` (cell 1).
- **Why it might help:** central planets reach more orbital options in fewer turns; the heuristic captures positional value v1.5G ignores.
- **Fit with v1.5G:** one-line multiplier inside the offense target-scoring function.
- **Cost:** trivial (minutes).
- **Regression risk:** low (multiplier on existing score; can be A/B'd via toggle).

### 3. Opponent-aggression scaling for defense reserves
- **Source:** mdmahfuzsumon (cell 1).
- **Why it might help:** binary aggressiveness signal is a cheap way to dynamically tune the defense/offense split.
- **Fit with v1.5G:** compute `enemy_in_flight / enemy_garrison` ratio in `WorldModel`; multiply `find_threats` defense reserve by 1.5 when above threshold.
- **Cost:** low (one-pass scan of obs.fleets + a multiplier).
- **Regression risk:** low.

### 4. Vulnerability-window target boosting
- **Source:** omega-v5 `detect_vulnerable_planets` (cell 16, 676-688).
- **Why it might help:** captures a real game state (enemy planet just spent its ships → temporarily exposed) that nobody else in the peer set tracks. Feeds attractive targets to the offense planner.
- **Fit with v1.5G:** add fleet-departure tracking to `WorldModel`; flag enemy planets whose recent garrison drop exceeds threshold; multiply their target value by ~2-3 (omega-v5 stacks 2.80 × 2.20 = 6×, almost certainly too aggressive).
- **Cost:** low-moderate (turn-over-turn diff + scoring multiplier).
- **Regression risk:** low if multiplier kept conservative.

### 5. Sun-tangent bypass routing
- **Source:** omega-v5 `bypass_angle` (cell 16, 430-454).
- **Why it might help:** v1.5G currently aborts sun-blocked launches. Bypass routing recovers some of those launches.
- **Fit with v1.5G:** add as a fallback after the direct-aim sun-collision check fails; route fleet via tangent waypoint, fall back to abort only if both CW and CCW tangent paths still collide.
- **Cost:** moderate (a few hours — geometry + integration with existing aim selection).
- **Regression risk:** low (strictly opens up more launches; existing abort path remains valid fallback).

### 6. Multi-enemy stacked-arrival defense buffer
- **Source:** johnjanson `_multi_enemy_proactive_keep` (cell 0).
- **Why it might help:** complements our forecast-flip defense by reserving ships against a temporal *stack* of inbound fleets, not just the worst single forecast deficit.
- **Fit with v1.5G:** sliding 3-turn window scan over `WorldModel.base_timeline` arrival ledger, sum enemy ship arrivals per window, reserve ~20% of largest window.
- **Cost:** low-moderate.
- **Regression risk:** low.

### 7. Crash-exploit detection (FFA-specific)
- **Source:** johnjanson `detect_enemy_crashes` (cell 0).
- **Why it might help:** purely additive opportunism in 4-player games; CLAUDE.md flags absence of FFA-aware logic as a v1.5G gap.
- **Fit with v1.5G:** detect two enemy fleets from different owners arriving at same target within 2 turns; queue a follow-up launch one turn after their predicted crash to claim wreckage.
- **Cost:** moderate — requires inferring enemy fleet destinations (which v1.5G doesn't currently do; see #8 below) and a new mission type.
- **Regression risk:** low if gated to only fire when crash is high-confidence.

### 8. Inferred enemy fleet destinations
- **Source:** rahulchauhan016 `_tgt(f)` (cell 7) — bearing-alignment heuristic, threshold 0.28 rad.
- **Why it might help:** prerequisite for #7 (crash detection) and improves general threat detection (we currently know only OUR fleet destinations).
- **Fit with v1.5G:** add as a helper to `WorldModel`; precompute predicted destinations once per turn for all non-self fleets.
- **Cost:** low.
- **Regression risk:** low.

### 9. Speed-optimal over-commit
- **Source:** omega-v5 `speed_optimal_send` (cell 16, 384-405).
- **Why it might help:** directly exploits the log-1.5 fleet-speed curve documented in CLAUDE.md — sometimes sending more ships than needed wins more turns of production at the destination than the extra cost.
- **Fit with v1.5G:** during launch sizing, compare `(needed, eta_at_needed)` vs `(0.92 * available, eta_at_overship)`; over-commit if the larger fleet saves ≥1 turn.
- **Cost:** moderate (recompute fleet_speed for hypothetical sizes; integrate with sizing logic).
- **Regression risk:** moderate — over-committing leaves source garrison thinner; needs reserve interaction.

### 10. Eco-mode tiering / death-ball endgame
- **Source:** omega-v5 (cell 16, 754-840).
- **Why it might consider:** gives the agent phase-aware behavior (snowball / panic / aggro / etc) that our static `HeuristicConfig` lacks.
- **Fit with v1.5G:** would require a state machine and per-mode tuning surface; significant architectural addition.
- **Cost:** high (full state machine + per-mode tuning).
- **Regression risk:** high — large tuning surface, many ways to misbehave; omega-v5 itself ranks below us with this in place.
- **Verdict:** defer unless other ideas plateau.

## Things explicitly NOT worth pursuing

- **DQN on a fabricated environment** (rauffauzanrambe): toy 6-action HP-and-movement env, no `kaggle_environments` integration, no `agent(obs)`. The "neural" framing is portfolio scaffolding, not transferable to the real game. Confirms that "neural" titles in this competition can be aspirational.
- **MCTS + beam search + 14-feature MLP "kitchen-sink" stack** (rahulchauhan016): 50 cells of complexity, ~691.2 ladder score with a silently dead neural gate (`NEURAL.predict` inside bare `try/except: pass`; `NeuralVal` not in cell 49's `CLASSES` export). The complexity:result ratio is bad. The CFR pruning *idea* (#11) is interesting in isolation but doesn't justify importing the stack.
- **Eco-mode state machine** (omega-v5, deep dive #10): high complexity, high tuning surface, source author ranks below us.
- **Planet triage / abandon-weak** (omega-v5): contradicts our defense-everything posture; high regression risk; only sourced from a below-us peer.
- **The fedorbaart visualizer dataset** (without separate pull): we'd need to pull the un-attached `fedorbaart/orbit-wars-visualizer` dataset to evaluate. Author's actual 850.9-scoring agent is in a *different* submission; this notebook gives no insight into it. Defer unless we want to specifically prospect their viz library for diagnostic-tooling ideas.
- **Marketing-driven prioritization.** 4 of 6 titles overclaim. Don't read titles; read code.

## Sparring-partner notes

- **mdmahfuzsumon** (rank 498, score 796.8) is the only credible candidate for porting as a local opponent. Single `%%writefile submission.py` cell — extracts cleanly. Importantly: this author *outscores us on the real ladder*. Adding this opponent to `src/orbit_wars/opponents/` would unstick CLAUDE.md's "local opponent pool is all-beaten 100%" complaint at least partially. Caveat: this is a snapshot test partner, not a tunable opponent — their constants are baked in, and we'd be vendoring third-party code so attribution and license handling matter.
- **johnjanson** (rank 672, score 747.8): also a single-cell submission, but ~1500 LOC and ranks below mdmahfuzsumon. If we want one peer opponent, mdmahfuzsumon is a better choice; if we want two for diversity, johnjanson is the runner-up.
- **omega-v5, rahulchauhan016, rauffauzanrambe, fedorbaart**: skip. Either too complex, score below us, or aren't agents at all.

## Open questions / follow-ups

- **Is v1.5G's `path_collision_predicted` over-conservative?** Multiple higher-scoring peers skip it entirely. Worth instrumenting: per-game count of launches we abort due to predicted collision, then re-run those launches in a counter-factual harness to see how many would actually have collided. If hit rate is low, we're losing tempo for false safety.
- **Which form of multi-source coordination is best?** Paired pincer (mdmahfuzsumon, no sync) vs three-source (johnjanson, with dominance check) vs arrival-time-matched (none of these notebooks). Probably worth implementing the simplest first (mdmahfuzsumon-style, no sync) and measuring before adding sync logic.
- **Does map-control bonus correspond to a real game principle**, or is it a confounding correlate of "near-center planets are also attacked more, so defending them feels valuable"? Could be tested by adding the bonus and measuring whether central planets are actually held longer.
- **Is the Hungarian-vs-greedy A/B already settled by ladder evidence?** None of the six peers use Hungarian. Indirect evidence for v1.5G's greedy default but not proof; the `use_hungarian_offense=True` toggle is still worth a controlled ladder run if we have submission slots to spare.
- **Do any of these techniques compound, or do they cancel?** The synthesis ranks them individually; it can't predict interactions. A Phase-2 brainstorm needs to pick 1-3 to prototype together and design the A/B harness.
- **Should we pull `fedorbaart/orbit-wars-visualizer` separately?** Worth a quick prospect pass for diagnostic-tooling ideas (APM sparklines, combat impact effects).

## Overall summary + thoughts

**Where we sit.** Our v1.5G at ~600-655 μ is in the middle of the peer cohort represented here (rank 318-988, scores 616-850). We are not behind public peers. We are not ahead. The top of the ladder (1623.1) is twice our score and represented by **none** of these six notebooks — top-10 players don't share their code.

**What we actually got from this research.** Useful directional hints, none of them silver bullets:
- 3 strong cross-codebase signals (multi-source coordination, opponent-behavior modeling, per-planet timeline simulation),
- 9 ranked single-technique candidates above (8 actionable + 1 deferred) by evidence × fit × cost,
- 1 credible sparring-partner candidate (mdmahfuzsumon),
- 1 surprising counter-finding (peers with weaker path-clearance score higher) that warrants its own investigation.

**The most uncomfortable finding.** Two of the higher-scoring peer agents (mdmahfuzsumon 796.8, johnjanson 747.8) violate the path-collision rule we treat as load-bearing in v1.5G. Either (a) the rule's enforcement matters less in practice than we assumed, (b) ladder matchmaking is favorable for naive aim, or (c) these authors are winning despite the bug because of compensating advantages. Until we measure, we don't know which. This is the highest-leverage open question for our submission.

**What this research does NOT give us.** The path to top-10. None of the public notebooks at our skill tier appears to contain a winning architecture. A top-10 finish probably requires either (a) something none of these notebooks try (search-based planning that actually works, RL on the real env, FFA-aware kingmaker logic) or (b) extreme polish on heuristics we already have. The hints above can move us a few hundred μ; getting from ~655 to top-10 (~1623+) is a different research project.

**Recommendation for Phase 2 brainstorm.** Pick a small bundle (probably 2-3 techniques) from the top of the ranked list and prototype them as a parallel `src/main.py` variant. Add mdmahfuzsumon as a sparring partner first so we can A/B locally with at least one above-us opponent. Then ladder-test with the variant against current v1.5G. Don't try all 9 at once.

**Priority ordering for Phase 2 candidates** (subject to your call):
1. Add mdmahfuzsumon as a local sparring partner (sample-size signal unlock).
2. Implement multi-source paired pincer (mdmahfuzsumon-style, no arrival sync) — addresses CLAUDE.md gap, sourced from above-us peer.
3. Add map-control bonus + opponent-aggression defense scaling — both trivial, both from same above-us source.
4. Instrument path-collision aborts to test whether they're costing us tempo.
5. Vulnerability-window scoring as a separate experiment.

Everything else: defer pending Phase 2 experiment results.

---

## Red-team review

*Independent critique by a fresh-context reviewer. Date: 2026-05-01.*

### Concerns

1. **"3 of 4 functional agents do multi-source" is overstated (TL;DR #1, line 10; pattern §, line 21).** The mdmahfuzsumon and johnjanson briefs explicitly describe pincer / 3-source swarms. The rahulchauhan016 brief describes MCTS with a per-source candidate pool ("nearest-7 enemies/neutrals per source", brief line 19) — that is per-source, not multi-source coordination. Calling MCTS "implicit multi-source" is the synthesis's inference, not the brief's claim. Honest count is 2/4 explicit + 1 unclear. Weakens but does not kill the pattern signal.

2. **The "simpler path-clearance correlates with higher score" finding (TL;DR #2, line 11; pattern §, lines 26-30) is n=3 and badly confounded.** The synthesis itself flags "skill gaps, opponent matchmaking, small sample" then still leads with this in the TL;DR and lists "instrument path-collision aborts" as Phase 2 priority #4. With n=3 across very different agents, this is one anecdote dressed up. The framing in §"Most uncomfortable finding" (line 151) — "the rule we treat as load-bearing" — risks motivating a regression-prone change. Fine to instrument; do NOT let it justify weakening `path_collision_predicted` without measurement.

3. **mdmahfuzsumon is over-weighted because it's the only above-us peer (n=1 selection bias).** Three of the top 5 ranked techniques (#1 pincer, #2 map-control, #3 aggression scaling) all come from this single source. The "evidence × fit × cost" framing implies multi-source corroboration; in fact items #2 and #3 have evidence = "one author who outscores us by ~140μ." If mdmahfuzsumon's score is partly luck/matchmaking rather than skill, the entire top-3 collapses. The synthesis should disclose this concentration explicitly.

4. **"Add mdmahfuzsumon as sparring partner FIRST" (Phase 2 step 1) burns a step that could be parallel.** Vendoring a third-party agent for local A/B is useful, but it has zero ladder impact — it just unsticks local signal. The same calendar week could spend a submission slot on the trivially-cheap map-control bonus toggle (#2, "minutes" cost) and get real ladder data. Recommend swapping order: ship the cheapest A/B-able single-line change, gather ladder evidence in parallel with the sparring-partner port.

5. **No discussion of the ~3 submissions/day budget constraint from CLAUDE.md.** Phase 2 lists 5 items but doesn't translate to "X submission slots over Y days." With ~3/day and ladder noise (CLAUDE.md notes v1.5 went 600→655 with more games — sample variance unresolved), each candidate plausibly needs 5-10 submissions to differentiate. The synthesis implicitly assumes plenty of slots.

6. **"All 6 authors verified against leaderboard.csv" (line 6) is technically false.** rauffauzanrambe is not on the leaderboard (per their own brief). Minor, but it's the kind of overstatement the synthesis correctly criticizes others for in TL;DR #5.

### Things the synthesis got right that should be preserved

- Skepticism of marketing titles and "neural" framings. The rauffauzanrambe and rahulchauhan016 dismissals are well-supported by their briefs and save real dev time.
- The "we are middle of cohort, top-10 needs something none of these notebooks have" framing (lines 143, 153) is honest and resists silver-bullet thinking.
- Deferring eco-mode state machine (#10) is correctly justified — high tuning surface, source author below us.

### Suggested edits to the Phase 2 priority ordering

Reorder to:
1. **Map-control bonus** (was #3) — minutes of work, single toggle, ladder-testable immediately.
2. **Add mdmahfuzsumon sparring partner** (was #1) — runs in parallel to #1's ladder games.
3. **Instrument path-collision aborts** (was #4) — measure BEFORE acting on the n=3 finding.
4. **Multi-source paired pincer** (was #2) — moderate cost, defer until after #1/#3 yield signal so we can isolate effect.
5. Defer everything else pending results.

Rationale: front-load the cheapest ladder-testable change so submission slots start producing data on day 1. Don't let "build infrastructure first" delay real measurement.
