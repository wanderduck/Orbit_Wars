# E2: competition-rules

## Source
/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/competition_documentation/Orbit_Wars-competition_overview_and_rules.md : "# Orbit Wars: Kaggle Competition Rules"

(Section spans lines 257-482; the level-1 heading is at line 257, immediately after the `---/---/---` separator at lines 251-253.)

## Fetch method
Read

## Goal
Document the binding legal and procedural constraints that apply to Orbit Wars submissions — what we can use to build the agent, what we owe Google/Kaggle if we win, what the agent is forbidden from doing during evaluation, and the operational constraints (submission rate, team size, timeline) that shape our development cadence. The competition is sponsored by Google LLC (line 277), with $50,000 in total prizes split as $5,000 per place across the top 10 (lines 287-298).

## Methods
Procedural rules extracted from the section:

- **Entry** (lines 261, 267): Entry constitutes acceptance of the Official Competition Rules. Single Kaggle account only — multi-account entry is prohibited.
- **Team formation** (line 314, line 431): Maximum team size is 5. One person may join only one Team. Team mergers are allowed by the Team leader, subject to a combined-Submission-count cap (see Numerical params).
- **Submissions** (line 318): 5 Submissions per day; 2 Final Submissions selectable for judging. The "Hackathons: 1 Submission only" clause does not apply — Orbit Wars uses the standard simulation-leaderboard structure.
- **Validation episode** (line 33): Each Submission first plays a self-play validation episode; if it fails, the Submission is marked Error before joining the pool.
- **Ranking** (lines 39, 388-390): Skill rating is Gaussian N(μ, σ²), updated per episode based on outcome and uncertainty. **No Private Leaderboard** in Simulation competitions (line 390); final standings come from public-leaderboard convergence.
- **Final Evaluation window** (line 41): After Final Submission Deadline, system runs additional games for ~2 weeks (until convergence), then leaderboard is locked.
- **Scoring** (line 191): Total ships on owned planets + ships in owned fleets at game end (or elimination); highest wins.
- **Tie-breaking** (line 439): Submission entered first wins.
- **Code sharing** (lines 431d, 435): No private sharing outside of Teams. Public sharing must be on Kaggle competition forum/notebooks and is deemed licensed under an OSI-approved license that does not limit commercial use.
- **Open source code in the model** (line 435c): Must be under an OSI-approved license that does not limit commercial use.
- **Eligibility** (lines 365-367, 402-415): Registered Kaggle account holder, 18+ (or local age of majority), not a resident of Crimea / DNR / LNR / Cuba / Iran / North Korea, not subject to U.S. export controls or sanctions. Employees, interns, contractors, officers, and directors of Google, Kaggle, and their parents/subsidiaries/affiliates **may enter but cannot win Prizes**.
- **Team prize splitting** (line 447f): Even shares between eligible Team members by default; unanimous opt-out for a different split is possible if Kaggle is notified before payout.
- **Governing law** (line 386): California law; exclusive venue in Federal/State courts of Santa Clara County.
- **Disqualification levers** (lines 441-443, 475): Cheating, deception, harassment, or attempts to undermine the competition can lead to disqualification and removal from the leaderboard.

## Numerical params / hyperparams

- **Total prize pool**: $50,000 (line 287)
- **Prize per place**: $5,000 each for places 1-10 (lines 289-298)
- **Maximum team size**: 5 (line 314)
- **Submissions per day**: 5 (line 318)
- **Final Submissions selectable**: 2 (line 318)
- **Team merger cap**: combined Submissions count <= (Submissions/day) x (days competition has run) at the Team Merger Deadline (line 314)
- **Initial skill rating**: μ₀ = 600 on first acceptance into the pool (line 33); skill modeled as Gaussian N(μ, σ²) (line 31)
- **Start Date**: April 16, 2026 (line 45)
- **Entry Deadline**: June 16, 2026 (line 47)
- **Team Merger Deadline**: June 16, 2026 (line 49)
- **Final Submission Deadline**: June 23, 2026 (line 51)
- **Leaderboard convergence window**: June 24, 2026 → ~July 8, 2026 (line 53)
- **All deadlines**: 11:59 PM UTC on the stated day unless noted (line 56)
- **Notification response window**: 1 week (line 443b)
- **Prize-document return window**: 2 weeks after notification (line 447d)
- **Prize payout window**: ~30 days after Sponsor/Kaggle receives required documents (line 447d)
- **Game step limit (engine context)**: 500 turns (line 188)
- **Per-turn timeout**: actTimeout = 1 second (line 243)

## Reusable code patterns
n/a (this section is legal/procedural, not code)

## Reported leaderboard score
n/a

## Anything novel worth replicating
Constraints we must respect in our codebase:

1. **Hard offline constraint at evaluation time** (line 398, "NO INGRESS OR EGRESS"): The agent cannot make any outbound network calls, fetch remote weights, hit an LLM API, query a database, or write to any external sink while an episode is being scored. Practical implications:
   - All model weights, lookup tables, opening books, and configs must be packaged inside the Submission artifact.
   - No `requests`/`urllib`/`socket`/`subprocess` calls to external services in the agent's hot path.
   - No telemetry, no analytics beacons, no remote logging.
   - Any LLM-assisted strategy must be either (a) run offline to produce static artifacts that ship with the Submission, or (b) replaced with a distilled local model that fits the runtime sandbox.
   - The 1-second per-turn budget (line 243) independently rules out any "phone home" pattern.

2. **Winner license is CC-BY 4.0 on Submission AND source code** (line 341): If we place top-10, our winning agent code is published under CC-BY 4.0. Implications:
   - Avoid embedding proprietary code, vendored dependencies with restrictive licenses, or third-party assets we cannot relicense.
   - Keep agent code (relicensable under CC-BY) separate from private tooling/research scaffolding we don't want to publish.
   - All open-source dependencies in the model must be OSI-approved and not restrict commercial use (line 435c). This rules out GPL-only and copyleft-with-commercial-restrictions packages. MIT, Apache 2.0, BSD, and CC-BY are safe.
   - Pretrained models or input data with incompatible licenses are exempt from the relicensing requirement (line 345) but must be identified, and methodology must remain reproducible.

3. **External data is allowed but bounded by "Reasonableness"** (lines 350-358): We can train on/condition with self-play data, public game-AI literature, free APIs, and small-cost subscriptions (Gemini Advanced is the cited boundary). We cannot rely on a proprietary dataset whose license cost exceeds the $5,000 prize. AMLT (Google toML, H2O Driverless AI, etc.) is explicitly permitted (line 363).

4. **Reproducibility deliverable for winners** (lines 348, 373): Detailed methodology required — architecture, preprocessing, loss, training details, hyperparameters — plus a code repo link with reproduction instructions. Keep training/eval scripts and seed configs version-controlled and documented from day one.

5. **Replays are public** (line 394): Anyone can download replays of our episodes. Strategy is observable to opponents over time — plan for opponents to study late-stage agents and adapt.

6. **Submission cadence** (line 318): Five submissions/day is generous but finite; with the validation-episode delay before joining the pool (line 33), batch experiments rather than ad-hoc pushing. The team-merger cap (line 314) prevents stacking submissions across pre-merger accounts.

7. **No multi-account / private-sharing escape hatches** (lines 267, 431d): One Kaggle account per person; no private code sharing outside one's official Team. Sharing infrastructure with another competitor must go through a public forum post or a Team merger.

## Direct quotes / code snippets to preserve

- **2.12 NO INGRESS OR EGRESS** (line 398): "During the evaluation of an episode your Submission may not pull in or use any information external to the Submission and Environment and may not send any information out."

- **2.11 ENVIRONMENTS & PUBLIC AVAILABILITY** (line 394): "This Competition makes use of Kaggle Environments. Additional rules related to the Environment(s) used in this Competition are available on the Competition Website. A replay of each episode of the competition, which includes the actions taken by your Submission in the episode, may be publicly available and downloadable."

- **2.5 WINNER LICENSE — core grant** (line 341): "You hereby license and will license your winning Submission and the source code used to generate the Submission under [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.en)"

- **2.5 WINNER LICENSE — software exception** (line 343): "For generally commercially available software that you used to generate your Submission that is not owned by you, but that can be procured by the Competition Sponsor without undue expense, you do not need to grant the license in the preceding Section for that software."

- **2.5 WINNER LICENSE — incompatible-license exception** (line 345): "In the event that input data or pretrained models with an incompatible license are used to generate your winning solution, you do not need to grant an open source license in the preceding Section for that data and/or model(s)."

- **2.6 EXTERNAL DATA — base permission** (line 352): "You may use data other than the Competition Data ('External Data') to develop and test your Submissions. However, you will ensure the External Data is either publicly available and equally accessible to use by all Participants of the Competition for purposes of the competition at no cost to the other Participants, or satisfies the Reasonableness criteria as outlined in Section 2.6.b below."

- **2.6 EXTERNAL DATA — Reasonableness example** (line 358): "By way of example only, a small subscription charge to use additional elements of a large language model such as Gemini Advanced are acceptable if meeting the Reasonableness Standard of Sec. 8.2. Purchasing a license to use a proprietary dataset that exceeds the cost of a prize in the competition would not be considered reasonable."

- **2.6.c AMLT** (line 363): "Individual Participants and Teams may use automated machine learning tool(s) ('AMLT') (e.g., Google toML, H2O Driverless AI, etc.) to create a Submission, provided that the Participant or Team ensures that they have an appropriate license to the AMLT such that they are able to comply with the Competition Rules."

- **2.2 SUBMISSION LIMITS** (line 318): "a. You may submit a maximum of five (5) Submissions per day. b. You may select up to two (2) Final Submissions for judging."

- **2.1 TEAM LIMITS** (line 314): "a. The maximum Team size is five (5). b. Team mergers are allowed and can be performed by the Team leader. In order to merge, the combined Team must have a total Submission count less than or equal to the maximum allowed as of the Team Merger Deadline. The maximum allowed is the number of Submissions per day multiplied by the number of days the competition has been running."

- **2.10 SCORING (no Private Leaderboard)** (line 390): "Your Submissions will be scored based on their performance in an episode, and your performances in episodes will be aggregated to determine your position on the Leaderboard, in each case as described in the evaluation documentation on the Competition Website. There is no Private Leaderboard in Simulation competitions."

- **2.7 ELIGIBILITY (employee carve-out)** (line 367): "...employees, interns, contractors, officers and directors of Competition Entities may enter and participate in the Competition, but are not eligible to win any Prizes. 'Competition Entities' means the Competition Sponsor, Kaggle Inc., and their respective parent companies, subsidiaries and affiliates."

- **3.1.a Eligibility floor** (lines 406-409): registered Kaggle.com account holder; 18+ (or local age of majority); not a resident of Crimea / DNR / LNR / Cuba / Iran / North Korea; not subject to U.S. export controls or sanctions.

- **Single-account rule** (line 267): "You cannot sign up to Kaggle from multiple accounts and therefore you cannot enter or submit from multiple accounts."

- **3.5.d No private sharing** (line 431): "Private Sharing. No private sharing outside of Teams. Privately sharing code or data outside of Teams is not permitted. It's okay to share code if made available to all Participants on the forums."

## Open questions / things I couldn't determine

- Submission artifact size limit and packaging format are not stated in this section; they live on the Competition Website / starter kit (referenced at line 73). Need to fetch separately.
- Exact evaluation compute environment (CPU/RAM/disk, Python version, allowed packages, GPU availability) is not stated. The 1-second `actTimeout` (line 243) plus the no-ingress rule (line 398) imply CPU-only inference of bundled artifacts is the safe assumption — confirm against Kaggle Environments docs.
- "Reasonableness Standard of Sec. 8.2" is referenced at line 358, but Section 8.2 is not present in this document. The reference appears to be to an external Kaggle policy doc — track it down before depending on any paid external data/tool.
- Whether Gemini Advanced (or any LLM API) is usable only at training time, or also during offline artifact generation that ships with the agent, is implicit. Combined with 2.12, runtime LLM calls are clearly forbidden; offline use during development is the only safe path.
- Section 2.10 references "evaluation documentation on the Competition Website" (line 390); we should pull it to confirm the exact ranking-algorithm parameters (initial σ, σ-decay rate, β, draw probability) since only μ₀=600 appears in our docs.
- Section 2.8.a contains a duplicated/garbled passage at lines 375-377 (the AMLT clause appears twice and one copy is truncated mid-quotation). Worth flagging to the document author, but the substantive rule is clear from lines 363 and 377.
- The doc uses Hackathon-style "Public/Private Leaderboard" language elsewhere (e.g., line 439a) but line 390 explicitly states there is **no** Private Leaderboard in Simulation competitions. The implication — that final placement comes from public-leaderboard convergence rather than a held-out private set — is consistent but meta-strategically important: late-game tuning against observable opponents directly determines final standing.
