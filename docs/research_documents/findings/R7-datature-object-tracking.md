# R7: Object Tracking Algorithms (datature.io)

## Source
https://datature.io/blog/a-comprehensive-guide-to-object-tracking-algorithms-in-2025

## Fetch method
WebFetch was DENIED on the comprehensive guide URL. Playwright `browser_navigate` was also DENIED. Fallback used: `WebSearch` (allowed_domains=["datature.io"]) issuing four targeted queries that pulled extracted snippets from the comprehensive guide AND from sibling articles in Datature's tracking series:

- `https://datature.io/blog/a-comprehensive-guide-to-object-tracking-algorithms-in-2025` (the article R7 was asked about)
- `https://datature.io/blog/introduction-to-bytetrack-multi-object-tracking-by-associating-every-detection-box`
- `https://datature.io/blog/implementing-object-tracking-for-computer-vision`
- `https://datature.io/blog/introduction-to-multiple-object-tracking-and-recent-developments`

Coverage is therefore PARTIAL. Pull-quotes below come from the search-engine snippets; full equations, diagrams, and code blocks from the original Jupyter-notebook companion were NOT directly accessible.

The Write tool was also denied, so this report is returned inline rather than persisted to `docs/research_documents/findings/R7-datature-object-tracking.md`.

## Document type
Blog article (technical survey, vendor-authored, computer-vision MOT focus)

## Topic
A 2025 survey of multi-object tracking (MOT) algorithms in computer vision pipelines — comparing classical motion-model trackers (Kalman filter + Hungarian assignment) against the modern transformer / state-space-model / memory-based generation. Covers: SORT, DeepSORT, Norfair, ByteTrack, BoT-SORT, QDTrack, plus the 2024-2025 cohort SAMBA-MOTR, CAMELTrack, Cutie, DAM4SAM.

## Goal
Help CV engineers pick a tracker. Article frames the central trade-off as **inference speed vs. depth of feature reasoning** — i.e. how far up the cost curve do you need to climb before identity-switches stop happening in your scene. The corollary that matters for us: every algorithm in the survey exists because the underlying problem is *measurement-noisy and dynamics-unknown*. Orbit Wars has neither of those problems.

## Methods

### Group A — Kalman + IoU / Hungarian (the classics)

**SORT**
- Motion model: linear constant-velocity Kalman filter on bounding-box state `[x, y, s, r, ẋ, ẏ, ṡ]` (center, scale, aspect ratio, derivatives).
- Association: predict next-frame box, match detections to predictions by IoU, solve with Hungarian.
- Strength: trivially cheap, real-time on CPU.
- Weakness: no appearance model — ID switches under occlusion or near identity-similar neighbours; constant-velocity prior breaks on curved / accelerating motion.

**DeepSORT**
- Adds a learned re-identification CNN; association is a cascade over Mahalanobis-gated motion + cosine-distance appearance.
- Strength: best recovery of long-occluded targets among the classical group.
- Weakness: needs a feature-extractor forward pass per detection; embeddings are scene-specific.

**Norfair**
- Lightweight Python tracker, distance-based matching, point or box. Tunable detection-interval tolerance.
- Strength: easiest to embed; tolerates skipped frames better than raw IoU.
- Weakness: still motion-model driven, no learned appearance by default.

**ByteTrack** (article's most-discussed classical)
- Two-stage association: high-confidence detections matched first to tracklets via IoU on Kalman-predicted boxes; low-confidence detections matched against unmatched tracklets in a second pass.
- Motion model assumption: standard Kalman, *uniform* (constant-velocity) motion.
- Strength: state-of-the-art among "simple" trackers; recovers detections normally thresholded away.
- Weakness (quoted): "relies primarily on spatial consistency through IoU matching, which limits its ability to maintain long-term identity preservation. It lacks learned representations for objects, making it vulnerable in scenarios with complex motion patterns or visually similar objects." Performance degrades in dance / crowded sport scenes. Does not natively support multi-class tracking.

**BoT-SORT**
- ByteTrack + Camera Motion Compensation (CMC) for non-uniform / ego-moving scenes.
- Article: "Since the Kalman filter is a uniform motion model, BOT-SORT adds CMC, which makes the predicted frame of the target not lead or lag when the target moves at a non-uniform speed."
- Weakness: "When the video resolution is large, CMC will greatly increase the time-consuming."

**QDTrack**
- Quasi-Dense contrastive feature learning; "Prediction boxes are matched with existing tracklets by the Hungarian algorithm which maximizes the overall instance similarity of QD embeddings."

### Group B — Transformer / SSM / Memory-based (2024-2025 cohort)

**SAMBA-MOTR** (~16 FPS) — Synchronized state-space models with selective memory updating; models inter-object dependencies and motion patterns jointly. Heavy.

**CAMELTrack** (~13 FPS) — Transformer-based contextual association; dynamically reweights motion vs. appearance vs. other cues per scene. Training-data hungry; black-box.

**Cutie** — Object-level query-based association combined with pixel-level memory. High-level identity reasoning while keeping spatial detail.

**DAM4SAM** (~11 FPS) — Distractor-aware memory management; functionally divided memory components. Slowest of the cohort.

### Cross-cutting primitives
- **Hungarian algorithm** for one-to-one assignment between predicted tracklets and incoming detections, minimising total cost.
- **IoU score** as cheap geometric matching metric.
- **Cosine similarity / Mahalanobis** for appearance / motion-gated matching.
- **Two-stage / cascade matching** (ByteTrack, DeepSORT) — prioritise high-confidence / recently-seen tracklets, mop up with leftovers.

## Numerical params / hyperparams

- **FPS (4090-class GPU, MOT17-style benchmarks)**: SAMBA-MOTR 16, CAMELTrack 13, DAM4SAM 11. Classical trackers run at O(100s of FPS) on CPU but exact numbers were not in retrieved snippets.
- **Kalman state vector for SORT-family**: 7-dim `[x, y, s, r, ẋ, ẏ, ṡ]`, with aspect ratio commonly held constant in process noise.
- **ByteTrack confidence thresholds**: `T_high` and `T_low` define the two stages (specific defaults not retrieved).
- **DeepSORT cascade**: matching cascade by track age — oldest unmatched tracks get lower priority.
- **Detection-interval tolerance**: Norfair's headline tunable; how many missed frames before a tracklet is dropped.

Concrete numerical defaults (process-noise covariance Q, measurement-noise R, gating thresholds) were not in the retrieved snippets and would need a full fetch.

## Reusable patterns for our heuristic

Brutal truth first: **most of this article does not apply to Orbit Wars**. The trackers exist to solve a problem we do not have. We have:

- Perfect observations every turn (`obs.planets`, `obs.fleets` are ground-truth coordinates).
- Deterministic, closed-form dynamics: `obs.angular_velocity` × elapsed turns gives any orbiting planet's exact future position; comet trajectories are pre-determined; fleets fly straight lines at known speed (`speed = 1 + (max-1) * (log(ships)/log(1000))^1.5`).
- Discrete-time, fully-observable MDP — not a noisy filtering problem.

A Kalman filter would either be (a) the identity function (R → 0, Q → 0, posterior = measurement) or (b) actively *worse* than a closed-form forward step. We should not use one.

What IS reusable:

1. **Predict-then-decide pattern.** The article's universal pipeline — *predict tracklet positions at the next frame before associating detections* — maps onto our agent loop: *predict planet/comet/fleet positions at turn `t + Δ` before deciding what to launch at*. Build a `predict_position(entity, dt)` helper:
   - Orbiting planet: rotate `(x − cx, y − cy)` by `angular_velocity × dt` around `CENTER`.
   - Comet: index a (deterministic) comet path table by `turn + dt` and clip if the comet leaves the board.
   - Fleet: `pos + dt × speed × unit_velocity` with the size-dependent speed formula above.

2. **Hungarian assignment for fleet→target dispatch.** This is the one algorithm that transfers wholesale. We have N owned planets with surplus garrison and M attractive targets. Build cost matrix `C[i,j] = travel_time(i,j) + λ × required_ships(j) − μ × strategic_value(j)` and solve with `scipy.optimize.linear_sum_assignment` for the best one-to-one launch plan. Replaces the current "nearest-planet sniper" baseline. `O((N+M)^3)` is fine for ≤ 20 planets within the 1-s actTimeout.

3. **Intercept solving (the thing tracking doesn't do for us, but is the natural next step).** Given a fleet aimed at a moving planet, solve `‖fleet_pos(t) − planet_pos(t)‖ = 0` for the launch direction. For circular-orbit planets this is a transcendental equation `‖p₀ + t·v − (cx + r·cos(θ₀ + ω·t), cy + r·sin(θ₀ + ω·t))‖ = 0` solved by 1-D root-finding (Brent / bisection over arrival time `t`, then back out launch heading). This is the Orbit-Wars analogue of Kalman-predict-then-IoU-match: aim at *where the planet will be*, not where it is.

4. **Two-stage / cascade association (ByteTrack idea).** Translates to *tiered targeting*: pass 1 commits surplus garrisons to highest-value capturable planets; pass 2 uses leftover small fleets on opportunistic mop-up (lone enemy garrisons of size 1, undefended comet pickups). Mirrors ByteTrack's "use the low-confidence detections too" principle.

5. **Gating before assignment (Mahalanobis-gating analogue).** Kalman filters gate matches by χ² distance to reject implausible pairings before Hungarian. Our analogue: prune the cost matrix to (i, j) pairs where (a) we have enough ships to win on arrival, (b) the path doesn't pass within `r_sun` of the sun (destroys the fleet), and (c) ETA is below a horizon. Gating before assignment keeps the optimiser from ever proposing dominated launches.

6. **What NOT to take.** Do not import a Kalman filter library. Do not import a CV tracker. Do not implement transformer-based association — SAMBA / CAMEL / Cutie / DAM4SAM are entirely off-budget for a 1-s heuristic and answer questions we don't have. Do not reach for re-id appearance features; entity IDs are given to us by the environment.

## Direct quotes / code snippets to preserve

> "Object or instance association is usually done by predicting the object's location at the current frame based on previous frames' tracklets using the Kalman Filter followed by one-to-one linear assignment typically using the Hungarian Algorithm to minimise the total differences between the matching results."

> "Since the Kalman filter is a uniform motion model, BOT-SORT adds camera motion compensation (CMC), which makes the predicted frame of the target not lead or lag when the target moves at a non-uniform speed."

> "[ByteTrack] relies primarily on spatial consistency through IoU matching, which limits its ability to maintain long-term identity preservation. It lacks learned representations for objects, making it vulnerable in scenarios with complex motion patterns or visually similar objects."

> "When the video resolution is large, CMC will greatly increase the time-consuming."

> "Norfair's tolerance for detection interval is greater than IOU, while DeepSORT performed the best, working well for rematching goals that haven't been seen for a long time."

No code snippets were retrievable via search-snippet fallback; the companion notebooks are linked from `/blog/implementing-object-tracking-for-computer-vision` but their content was not accessible.

## Anything novel worth replicating

- **The two-stage ByteTrack pattern** is the highest-leverage idea in the article and ports cleanly to a tiered targeting scheme (see Reusable Patterns #4).
- **CAMELTrack's dynamic cue reweighting** is interesting as inspiration only: the heuristic equivalent is making `λ`, `μ` in the cost matrix depend on game phase (early-game expansion, mid-game contesting comets, late-game elimination). Not novel, but a useful reminder that fixed weights are a known weakness.
- Nothing in SAMBA-MOTR / Cutie / DAM4SAM is replicable inside a 1-s heuristic budget. Skip.

## Open questions / things I couldn't determine

1. **Exact Kalman state-update equations** — article reportedly contains equations, but the search-snippet fallback returned only narrative prose. Standard SORT equations are easily found elsewhere if needed; not a blocker.
2. **Concrete hyperparameters** for ByteTrack `T_high`/`T_low`, DeepSORT cosine threshold, Norfair distance threshold — not retrieved.
3. **Code snippets** from the companion blog `/implementing-object-tracking-for-computer-vision` — confirmed to exist (Jupyter notebook with IoU / Norfair / DeepSORT side-by-side) but not accessed.
4. **Whether the article discusses single-object trackers** (KCF, CSRT, ECO, DiMP, ToMP) is unclear — snippets only surfaced MOT methods. SOT methods are arguably closer to our use case (known target ID, predict where it will be) but coverage was not confirmed.
5. **The Kalman state used in the survey's figures** — bbox-state (SORT-style 7-D) or extended to curvilinear / angular-velocity states? Probably the standard 7-D given focus on existing trackers, but unconfirmed.

Unblock would require WebFetch or Playwright permission, both of which were denied in this run.

## Relevance to Orbit Wars (1-5)

**2 / 5.**

The article's core problem (associating noisy detections to tracklets across frames under uncertain motion) is not our problem. We have ground-truth observations and closed-form dynamics; a Kalman filter degenerates to identity, and a re-id network is meaningless. The dominant value-add for our agent is one transferable algorithm (**Hungarian / linear-sum assignment** for fleet→target dispatch) plus one transferable design pattern (**predict-then-decide**, manifesting as a `predict_position(entity, dt)` helper plus an intercept solver for moving planets). Those are real but small. Everything in the modern transformer/SSM/memory cohort is irrelevant to a 1-second heuristic. A heuristic-algorithms survey or a pursuit-evasion / interception-geometry source would score 4-5 on the same scale; this CV-MOT survey scores 2.
