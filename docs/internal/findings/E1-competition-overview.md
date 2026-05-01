# E1: competition-overview

## Source
/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/competition_documentation/Orbit_Wars-competition_overview_and_rules.md : "# Orbit Wars: Kaggle Competition Overview"

## Fetch method
Read

## Goal
This section is a player-facing overview of the Orbit Wars Kaggle competition. It tells the reader (a) what Orbit Wars is — a multi-agent 1v1 or 4-player FFA bot competition inspired by the 2010 Planet Wars challenge (lines 19, 23) — (b) how submissions are evaluated on a TrueSkill-style ladder using a Gaussian skill rating with N(mu, sigma^2) (lines 27-39), (c) the key dates and prize structure ($5,000 for each of 1st-10th place, $50,000 total) (lines 43-69), and (d) the full game mechanics required to write an agent: the 100x100 continuous board with a sun at center, planet/fleet/comet definitions, fleet speed/movement formulas, turn order, combat resolution, scoring/termination rules, the observation schema, the action format, and the default configuration parameters (lines 79-247). It is, in effect, the technical spec a competitor needs before reading the starter kit.

## Methods
- Ladder-based skill evaluation across submitted bots (line 27): each daily team can submit up to 5 agents; only the latest 2 submissions are tracked for final scoring (line 27).
- Validation Episode against self-copies on upload; failures mark the Submission as Error and produce downloadable agent logs; successful validation initializes mu0 = 600 and adds the bot to the All Submissions pool (line 33).
- Matchmaking by similar rating with extra episodes for new bots (line 35).
- Ranking update rule (line 39): wins increase mu and decrease opponent mu; draws move both mu values toward their mean; magnitudes scale with deviation from expected and with sigma; sigma reduces with information gained; score margin does not affect updates.
- Final evaluation: submissions lock at the deadline; ladder runs another ~2 weeks before final leaderboard freezes (line 41, line 53).
- Game-engine mechanics (lines 79-191):
  - Continuous 100x100 board, origin at top-left, sun at (50, 50) with radius 10; fleets that cross the sun are destroyed (lines 85-86).
  - 4-fold mirror symmetry for placement: `(x, y), (100-x, y), (x, 100-y), (100-x, 100-y)` (line 87).
  - Planet representation: `[id, owner, x, y, radius, ships, production]` (line 91); owner in {0..3} or -1 neutral; radius = 1 + ln(production); production integer 1..5; initial ships in [5, 99] skewed low (lines 93-96).
  - Orbiting iff `orbital_radius + planet_radius < 50`; angular velocity 0.025-0.05 rad/turn randomized per game (line 100). Static otherwise (line 101). 20-40 planets total (5-10 symmetric groups of 4); >=3 static groups, >=1 orbiting group (line 103).
  - Home planets: one symmetric group randomly chosen; 2P games use diagonal Q1/Q4; 4P uses one planet per player from the group; home planets start with 10 ships (line 107).
  - Fleet representation: `[id, owner, x, y, angle, from_planet_id, ships]`; ship count invariant during travel (lines 111-114).
  - Fleet speed scales logarithmically with size (lines 118-126).
  - Straight-line travel; removed if out of bounds, crosses sun, or collides with any planet (combat trigger). Continuous collision detection along path segment (lines 128-136).
  - Launch action format: `[from_planet_id, direction_angle, num_ships]`; only from owned planets; cannot exceed garrison; spawns just outside planet radius along the angle; multiple launches per turn allowed (lines 140-145).
  - Comets: 4-per-quadrant groups spawn at steps 50, 150, 250, 350, 450; radius 1.0; production 1; starting ships are min of 4 rolls from 1-99 shared across the group; default speed 4.0 (lines 149-159). Comets follow normal planet rules. Removed-on-exit step happens before launches (line 157). `paths` and `path_index` enable prediction (line 159).
  - Turn order (lines 163-171): comet expiration → comet spawning → fleet launch → production → fleet movement → planet rotation & comet movement (sweeping fleets into combat) → combat resolution.
  - Combat resolution (lines 175-182): group arriving fleets by owner; largest minus second-largest survives; surviving attacker either reinforces (same owner) or fights garrison (different owner) and may flip the planet; attacker tie annihilates all attackers.
  - Termination (lines 186-191): 500-turn step limit, or one/zero players remain with planets/fleets; final score = ships on owned planets + ships in owned fleets; highest wins.

## Numerical params / hyperparams
- Daily submissions cap: 5/team (line 27).
- Tracked submissions for final ranking: latest 2 (line 27).
- Validation pass starting mu0 = 600 (line 33).
- Skill model: Gaussian N(mu, sigma^2) (line 31).
- Final submission deadline: June 23, 2026 (lines 41, 51); extra ~2 weeks of games after.
- Deadlines at 11:59 PM UTC unless noted (line 56).
- Timeline (lines 45-53): Start April 16, 2026; Entry & Team Merger Deadlines June 16, 2026; Final Submission Deadline June 23, 2026; ongoing games June 24 - approx July 8, 2026.
- Prizes: $5,000 each for places 1-10; total $50,000 implied (lines 60-69).
- Board: 100x100 continuous, origin at top-left (line 85; default `boardSize` 100.0 line 246).
- Sun: center (50, 50), radius 10; default `sunRadius` 10.0 (line 86, line 245).
- Symmetry mapping: `(x, y), (100-x, y), (x, 100-y), (100-x, 100-y)` (line 87).
- Planet count: 20-40 (line 103); >=3 static groups, >=1 orbiting group (line 103).
- Owner ID range: 0-3 with -1 neutral (line 93).
- Planet radius: `radius = 1 + ln(production)` (line 94).
- Production: integer in [1, 5] (line 95).
- Initial planet ships: [5, 99], skewed low (line 96).
- Orbiting condition: `orbital_radius + planet_radius < 50` (line 100).
- Angular velocity: 0.025-0.05 rad/turn, randomized per game (line 100).
- Home planet starting ships: 10 (line 107).
- Fleet speed formula (lines 121-122): `speed = 1.0 + (maxSpeed - 1.0) * (log(ships) / log(1000)) ^ 1.5`.
- 1-ship fleet speed: 1.0 units/turn (line 124).
- Default max fleet speed: 6.0; default `shipSpeed` 6.0 (line 125, line 244).
- ~500 ships → ~5 units/turn; ~1000 ships → max (line 126).
- Comet radius: 1.0 fixed (line 151).
- Comet production: 1 ship/turn (line 152).
- Comet starting ships: min of 4 rolls from 1-99 (skewed low); shared across group (line 153).
- Comet speed default: 4.0 units/turn; configurable via `cometSpeed` (line 154, line 247).
- Comet spawn steps: 50, 150, 250, 350, 450 (line 149).
- Game length: 500 turns (line 81, line 188; default `episodeSteps` 500 line 242).
- Per-turn act timeout: 1 second; default `actTimeout` 1 (line 243).
- Action angle convention: 0 = right, pi/2 = down (line 215).
- Empty action: `[]` (line 218).
- Player ID range: 0-3 (line 199).

Configuration table (lines 240-247): `episodeSteps`=500, `actTimeout`=1, `shipSpeed`=6.0, `sunRadius`=10.0, `boardSize`=100.0, `cometSpeed`=4.0.

Observation fields (lines 195-204): `planets` (`[[id, owner, x, y, radius, ships, production], ...]`), `fleets` (`[[id, owner, x, y, angle, from_planet_id, ships], ...]`), `player` (int), `angular_velocity` (float), `initial_planets` (same shape as `planets`), `comets` (`[{planet_ids, paths, path_index}, ...]`), `comet_planet_ids` (`[int, ...]`), `remainingOverageTime` (float).

## Reusable code patterns

Fleet speed formula (lines 120-122, fenced as ```apache):

```
speed = 1.0 + (maxSpeed - 1.0) * (log(ships) / log(1000)) ^ 1.5
```

Action format (lines 210-212, fenced as ```inform7):

```
[[from_planet_id, direction_angle, num_ships], ...]
```

Agent convenience snippet (lines 224-236, fenced as ```routeros):

```python
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet, CENTER, ROTATION_RADIUS_LIMIT

def agent(obs):
    planets = [Planet(*p) for p in obs.get("planets", [])]
    fleets = [Fleet(*f) for f in obs.get("fleets", [])]
    player = obs.get("player", 0)

    for p in planets:
        print(p.id, p.owner, p.x, p.y, p.radius, p.ships, p.production)

    return []  # list of [from_planet_id, angle, num_ships]
```

## Reported leaderboard score
n/a

## Anything novel worth replicating
- Continuous 100x100 board with continuous swept-segment collision detection (line 136) — agents need swept-volume reasoning, not grid-cell checks.
- Logarithmic fleet-speed scaling with explicit anchor points 1→1.0, 500→~5, 1000→~max (lines 121-126), creating a real ship-mass vs tempo tradeoff.
- Sun as destructive obstacle at the centre of the map (line 86) — encourages route planning around the sun and breaks naive straight-line attacks.
- Orbiting planets with predictable angular velocity exposed through `initial_planets` and `angular_velocity` (line 100), enabling forward-prediction; static planets identified via `orbital_radius + planet_radius < 50` (line 100).
- Comets as periodic, capturable, decaying resources spawned at deterministic steps with 4-quadrant symmetry and pre-computed `paths` + `path_index` (lines 149, 159).
- 4-fold mirror symmetry guaranteeing fairness (line 87), ideal for symmetric search and reflective value-network designs.
- Strict turn order (lines 163-171) where production happens AFTER fleet launches but BEFORE fleet movement — affects "snipe-on-launch" ship math.
- Combat: largest minus second-largest applied across all attackers (line 178); attacker ties annihilate (line 182). Strong incentive for coordination via single-ship "tip" fleets.
- 2P games always use diagonal Q1/Q4 home planets (line 107), narrowing the early-game scenario space and making opening books practical.
- mu0 = 600 (line 33) is a useful seed for any local self-play surrogate that mirrors the official ladder.
- Score-magnitude does not affect skill updates (line 39) — optimize for narrow, reliable wins rather than crushing-but-unstable wins.

## Direct quotes / code snippets to preserve

Line 19: "The goal of this competition is to create and/or train AI bots to play a novel multi-agent 1v1 or 4p FFA game against other submitted agents."

Line 27: "Each day your team is able to submit up to 5 agents (bots) to the competition. Each submission will play Episodes (games) against other bots on the ladder that have a similar skill rating. Over time skill ratings will go up with wins or down with losses and evened out with ties. To reduce the number of bots playing and increase the number of episodes each team participates in, we only track the latest 2 submissions and use those for final submissions."

Line 31: "Each Submission has an estimated Skill Rating which is modeled by a Gaussian N(mu, sigma2) where mu is the estimated skill and sigma represents the uncertainty of that estimate which will decrease over time."

Line 33: "When you upload a Submission, we first play a Validation Episode where that Submission plays against copies of itself to make sure it works properly. If the Episode fails, the Submission is marked as Error and you can download the agent logs to help figure out why. Otherwise, we initialize the Submission with mu0=600 and it joins the pool of All Submissions for ongoing evaluation."

Line 39: "After an Episode finishes, we'll update the Rating estimate for all Submissions in that Episode. If one Submission won, we'll increase its mu and decrease its opponent's mu -- if the result was a draw, then we'll move the two mu values closer towards their mean. The updates will have magnitude relative to the deviation from the expected result based on the previous mu values, and also relative to each Submission's uncertainty sigma. We also reduce the sigma terms relative to the amount of information gained by the result. The score by which your bot wins or loses an Episode does not affect the skill rating updates."

Line 41: "At the submission deadline on June 23, 2026, additional submissions will be locked. From June 23, 2026 for approximately two weeks, we will continue to run games. At the conclusion of this period, the leaderboard is final."

Line 81: "Players start with a single home planet and compete to control the map by sending fleets to capture neutral and enemy planets. The board is a 100x100 continuous space with a sun at the center. Planets orbit the sun, comets fly through on elliptical trajectories, and fleets travel in straight lines. The game lasts 500 turns. The player with the most total ships (on planets + in fleets) at the end wins."

Lines 85-87:
- "Board: 100x100 continuous space, origin at top-left."
- "Sun: Centered at (50, 50) with radius 10. Fleets that cross the sun are destroyed."
- "Symmetry: All planets and comets are placed with 4-fold mirror symmetry around the center: `(x, y), (100-x, y), (x, 100-y), (100-x, 100-y)`. This ensures fairness regardless of starting position."

Line 91: "Each planet is represented as `[id, owner, x, y, radius, ships, production]`."

Line 94: "radius: Determined by production: `1 + ln(production)`. Higher production planets are physically larger."

Line 100: "Orbiting planets: Planets whose `orbital_radius + planet_radius < 50` rotate around the sun at a constant angular velocity (0.025-0.05 radians/turn, randomized per game). Use `initial_planets` and `angular_velocity` from the observation to predict their positions."

Line 103: "The map contains 20-40 planets (5-10 symmetric groups of 4). At least 3 groups are guaranteed to be static, and at least one group is guaranteed to be orbiting."

Line 107: "One symmetric group is randomly chosen as the starting planets. In a 2-player game, players start on diagonally opposite planets (Q1 and Q4). In a 4-player game, each player gets one planet from the group. Home planets start with 10 ships."

Line 111: "Each fleet is represented as `[id, owner, x, y, angle, from_planet_id, ships]`."

Lines 121-122: `speed = 1.0 + (maxSpeed - 1.0) * (log(ships) / log(1000)) ^ 1.5`

Line 126: "A fleet of ~500 ships moves at ~5, and ~1000 ships reaches the max."

Line 136: "Collision detection is continuous -- the entire path segment from old to new position is checked, not just the endpoint."

Line 140: "Each turn, your agent returns a list of moves: `[from_planet_id, direction_angle, num_ships]`."

Line 144: "The fleet spawns just outside the planet's radius in the given direction."

Line 149: "Comets are temporary extra-solar objects that fly through the board on highly elliptical orbits around the sun. They spawn in groups of 4 (one per quadrant) at steps 50, 150, 250, 350, and 450."

Line 153: "Starting ships: Random, skewed low (minimum of 4 rolls from 1-99). All 4 comets in a group share the same starting ship count."

Line 157: "When a comet leaves the board, it is removed along with any ships garrisoned on it. Comets are removed before fleet launches each turn, so you cannot launch from a departing comet."

Line 159: "The `comets` observation field contains comet group data including `paths` (the full trajectory for each comet) and `path_index` (current position along the path), which can be used to predict future comet positions."

Lines 163-171 (turn order): "1. Comet expiration ... 2. Comet spawning ... 3. Fleet launch ... 4. Production ... 5. Fleet movement ... 6. Planet rotation & comet movement ... 7. Combat resolution".

Lines 175-182 (combat): "1. All arriving fleets are grouped by owner. Ships from the same owner are summed. 2. The largest attacking force fights the second largest. The difference in ships survives. 3. If there is a surviving attacker: - If the attacker is the same owner as the planet, the surviving ships are added to the garrison. - If the attacker is a different owner, the surviving ships fight the garrison. If the attackers exceed the garrison, the planet changes ownership and the garrison becomes the surplus. 4. If two attackers tie, all attacking ships are destroyed (no survivors)."

Line 191: "Final score = total ships on owned planets + total ships in owned fleets. Highest score wins."

Line 215: "direction_angle: Angle in radians (0 = right, pi/2 = down)."

Line 218: "Return an empty list `[]` to take no action."

Line 225: `from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet, CENTER, ROTATION_RADIUS_LIMIT`

## Open questions / things I couldn't determine
- "We only track the latest 2 submissions" (line 27) versus "Every bot submitted will continue to play episodes until the end" (line 29) — does "track" mean older submissions are removed from matchmaking, hidden from the leaderboard while still playing, or something else? Apparent contradiction is unresolved here.
- The mu update is described qualitatively (line 39) but the exact rating system (TrueSkill, OpenSkill, Glicko, custom) is not named, and sigma0 is never given (only mu0 = 600, line 33).
- "Evened out with ties" (line 27) is mentioned, but the section never defines a tie at the game level: lines 188-191 describe termination but do not address what happens if two players finish on identical final scores.
- Player IDs are stated as 0-3 (line 199), but for 1v1 matches the section doesn't specify whether IDs are {0, 1} or some other pair.
- "Fleets that cross the sun are destroyed" (line 86) — the section does not say whether the launching planet still benefits from production that turn (the turn order in lines 163-171 implies yes), nor whether destroyed ships are credited to anyone (presumably no, but unstated).
- Combat rule "largest fights second-largest" (line 178) — with 3+ attackers of distinct sizes, does the third attacker also engage the survivor, or is combat strictly pairwise leaving the third attacker destroyed? Wording is ambiguous.
- Home-planet selection (line 107) — is the chosen group guaranteed to be static, orbiting, or either? Unspecified.
- `remainingOverageTime` (line 204) implies a per-game time budget atop `actTimeout`=1s (line 243), but its size is not given here.
- Whether the official competition runs with the documented "Default" config values exactly (line 240) or whether they may be tuned at evaluation is not stated.
- Relationship between `comet_planet_ids` (flat list, line 203) and `comets[i].planet_ids` (per-group, line 202) is not explicit.
- `angular_velocity` is a single observation field (line 200), suggesting one global value per game; whether all orbiting groups share the same value or each group has its own is not stated explicitly.
- "Extra-solar objects" but with elliptical orbits around the sun (line 149) is mildly inconsistent terminology; entry/exit geometry is left to the `paths` data.
