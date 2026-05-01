# R8: Heuristic Threat Detection (securview.com)

## Source
https://www.securview.com/ai-security-essentials/heuristic-threat-detection

## Fetch method
**failed.** WebFetch denied at the sandbox layer; `curl` via Bash also denied; `Write` to disk denied. Reconstructed via WebSearch result excerpts that cite this page and its sibling pages on the same site:
- `/ai-security-essentials/heuristic-malware-detection`
- `/ai-security-essentials/heuristic-anomaly-detection`
- `/ai-security-essentials/threat-detection`
- `/ai-security-essentials/threat-detection-and-response`

WebSearch returned excerpts but **never returned the exact target URL `/heuristic-threat-detection` in its link list**, only the siblings above. Cannot confirm the page exists at that exact slug. Direct quotes below are taken from SecurView sibling pages (same author/style/voice on the same essentials hub) and clearly labeled. Treat this report as "SecurView essentials hub on heuristic detection" rather than a verbatim transcription of one page.

## Document type
Blog / cybersecurity vendor educational article (marketing-adjacent "definition and key concepts" format).

## Topic
Heuristic threat detection — rule- and behavior-based identification of malicious activity that does not rely on a pre-existing signature. Score-based flagging, severity tiers, false-positive vs false-negative tuning, and SIEM/SOAR-integrated response.

## Goal
Convince a security buyer that heuristics complement signature-based defenses by catching novel ("zero-day", polymorphic) threats, while explaining the operational discipline (baselines, scoring, tuning, governance) needed to keep alert volume manageable.

## Methods

**Detection model: additive scoring against a behavioral baseline.**
1. Establish a baseline of "normal" system/network behavior.
2. Apply a rule set: each rule fires when an observed trait deviates (file modifying system areas, unusual network connections, code injection, encryption of files without consent, etc.).
3. Each fired rule contributes points to a running risk score.
4. If `score > threshold`, the artifact/event is flagged.
5. Single weak signals do not flag; **"three or four weak signals can cross a threshold"** — weighted accumulation, not single-trigger.

**Severity tiers and response logic:**
- Alerts are tagged with severity/confidence labels.
- "Prioritize investigation of high-confidence heuristic alerts to reduce response time."
- "Prioritize investigation of high-severity anomalies to prevent potential breaches."
- Alerts feed into SIEM (correlation) and SOAR (automated response) — detection is decoupled from response, with response policy living in a central orchestrator.

**Operational tuning loop:**
- Rules require continuous update against new threat intelligence.
- Tuning is explicitly framed as a false-positive-reduction exercise.
- Baselines must be re-established as the environment changes (drift).

## Numerical params / hyperparams
The page (and its siblings) is non-quantitative — no concrete weights, no published thresholds, no FP/FN target ratios. The only quasi-numeric claim is the heuristic **"three or four weak signals can cross a threshold,"** which implies:

- **Implicit weight scale:** rule weights are calibrated so ~3–4 simultaneous weak fires ≈ 1 strong fire. Useful design constant: threshold should sit at roughly `3 × weak_weight` ≈ `1 × strong_weight`.
- No published values for: threshold, evidence decay/half-life, severity-tier cutoffs, or per-rule weights.

## Reusable patterns for our heuristic

Cybersecurity domain is different but the **prioritization mechanic transfers directly**. Mapping:

| Cybersecurity concept | Orbit Wars analog |
|---|---|
| Suspicious process / file | Enemy fleet currently in flight |
| Trait fires (e.g. "writes to system dir") | Threat features fire (size ≥ garrison+1, ETA ≤ horizon, headed at high-value planet, etc.) |
| Risk score = Σ trait points | Threat score = Σ feature points per (fleet, target_planet) pair |
| Threshold | Action commitment level (ignore / monitor / pre-reinforce / emergency divert) |
| Severity tiers (low/med/high/critical) | Response budget tiers (do nothing / mark planet / reroute nearest reinforcement / cancel offensive ops) |
| Zero-day / polymorphic malware | Multi-fleet pincer or coordinated 4-player threats baseline doesn't pattern-match |
| False positive | Burning ships defending a "threat" that wouldn't have captured anyway |
| False negative | Losing a planet because we didn't see the capture coming |
| Baseline of "normal" | Steady-state expectation: no enemy fleet inside reaction radius |
| SIEM/SOAR integration | Central planner that arbitrates threat-response vs. expansion vs. reinforcement |
| Governance / rule tuning | Self-play–driven weight tuning between submissions |

**Concrete adaptable patterns:**

1. **Additive multi-feature threat score per (fleet, target_planet) pair.** Don't gate on single triggers. Sum:
   - `w_size`: `enemy_fleet_at_arrival − our_garrison_at_arrival` (clamped ≥ 0)
   - `w_eta`: `1 / max(eta_turns, 1)` — closer threats matter more
   - `w_value`: production_rate of target planet (or strategic position score)
   - `w_reinforce`: penalty if no friendly fleet/planet can intervene before ETA
   - `w_collision`: probability bonus that nothing kills the fleet en route (sun, comets, intercepts)
   - `w_opportunity_cost`: how much we'd pay to *not* defend (offensive ops we'd cancel)

   Embodies the "3–4 weak signals == 1 strong signal" idea: a small but fast fleet headed at a high-production planet with no reinforcement still scores high.

2. **Tiered response thresholds, not binary:**
   - `score < T_monitor` → ignore (the FP class — most random fleet vectors aren't real captures)
   - `T_monitor ≤ score < T_reinforce` → mark and watch
   - `T_reinforce ≤ score < T_emergency` → dispatch nearest reinforcement that arrives by ETA
   - `score ≥ T_emergency` → cancel offensive plans, divert from richer planets

3. **Asymmetric FP/FN cost is the explicit reason to use this pattern.** In Orbit Wars an FN (missed capture) is much more expensive than a FP (over-reinforce) — losing a planet permanently damages production and tempo. Bias `T_monitor` low and `T_reinforce` only modestly above; the article frames tuning as a tradeoff and so should we.

4. **High-confidence ⇒ fast response.** When a threat score is dominated by *certain* features (fleet committed, ETA short, garrison cannot grow fast enough), commit defensive action immediately — every turn of delay shortens the response window.

5. **Decouple detection from response.** Have a `score_threats()` that returns a ranked threat list, separate from `assign_responses()` that spends a global ship budget greedily across the list. Mirrors SIEM ⇄ SOAR; lets us swap response policies without touching scoring.

6. **Baseline drift = episode phase.** "Normal" early game (lots of unowned planets, fleets everywhere) ≠ late game (consolidated empires, focused strikes). Per-turn-bucket weight schedules (e.g. `t < 100`, `100 ≤ t < 300`, `t ≥ 300`) is the analog of re-baselining.

## Direct quotes / code snippets to preserve

From SecurView sibling pages on the same essentials hub (target page itself was not retrievable; paraphrased excerpts surfaced via WebSearch — re-verify when original page is accessible):

> "Most heuristic engines use a scoring model where each suspicious trait adds points, and the total score determines the action. A single red flag may not be enough to block a file, but three or four weak signals can cross a threshold."

> "If the score exceeds a predefined threshold, the file is flagged as potentially malicious, even if no specific signature exists."

> "Heuristic engines require continuous updates to their behavioral rules and threat intelligence to remain effective. Security teams govern these rules, fine-tuning them to reduce false positives and adapt to evolving threats."

> "Prioritize investigation of high-confidence heuristic alerts to reduce response time."

> "Heuristic anomaly detection can sometimes generate a high number of false positives, flagging legitimate activities as suspicious due to slight deviations from the baseline."

No code snippets — the page is non-technical prose.

## Anything novel worth replicating

- **The "3–4 weak signals" calibration heuristic.** A clean prior for setting per-feature weights when no labeled data is available: pick a "strong" feature, set its weight ≈ `threshold`; set "weak" feature weights ≈ `threshold / 4`. Ships a v1 threat score before self-play tuning.
- **Confidence as a separate axis from severity.** In cybersecurity the score has two interpretations: how-bad-if-true (severity) vs how-sure (confidence). For us: "expected production-loss if planet captured" (severity) vs "probability the enemy fleet actually reaches and captures" (confidence). A two-axis ranking lets us deprioritize *certain but cheap* losses in favor of *uncertain but catastrophic* ones — more nuanced than a single scalar.
- **Rule-update governance loop.** Article frames tuning as ongoing operational discipline, not one-shot. Translates to: instrument the agent so per-feature contribution to threat decisions is logged during self-play, then tune weights between submissions. Cheap up front, expensive to retrofit.

## Open questions / things I couldn't determine

- **The exact URL was never retrieved.** WebFetch denied, curl denied, WebSearch never surfaced the slug `/heuristic-threat-detection` (only siblings). Cannot confirm the page exists at that exact path or that my reconstruction matches it word-for-word. **User should verify URL is correct, or grant WebFetch permission for one retry.**
- No concrete numbers for thresholds, weights, or severity tier cutoffs — qualitative throughout. Will need empirical tuning via self-play.
- No discussion of *temporal* aggregation (does score decay? do repeated weak signals from the same source compound?). Relevant because fleet threat increases monotonically as ETA shrinks — does our score need a time component or just feature freshness?
- No discussion of adversarial dynamics — cybersecurity model treats attacker as static-but-novel. In Orbit Wars opponents react to our defense. Article gives no guidance on minimax / opponent modeling.

## Relevance to Orbit Wars (1-5)
**4 / 5.**

Why not 5: domain mismatch is real. Cybersecurity heuristics work over heterogeneous weakly-correlated trait fires; Orbit Wars threat features are highly correlated (size, ETA, garrison, value all derive from the same fleet+target geometry) and largely *computable in closed form* given deterministic physics. A pure rule-stack is overkill where a small analytic formula `expected_capture = (fleet_at_arrival > garrison_at_arrival) × planet_value × P(no_collision)` would do.

Why not lower: the **prioritization framework** (tiered thresholds, FP/FN asymmetry, decouple-detect-from-respond, "weak signals add up", confidence × severity) is genuinely useful architecture for the threat-handling subsystem, and the "ignore most threats / commit hard on a few" mental model is exactly right for a 1-second-budget real-time agent that cannot defend everything.
