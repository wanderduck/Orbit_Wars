# E3: game-overview

## Source
`/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/competition_documentation/Orbit_Wars-game_and_agents_overviews.md` : "# Orbit Wars: Game Overview"

Section spans lines 15-188 (heading at line 15, terminated by `---\n---\n---` separator at lines 191-193).

## Fetch method
Read

## Goal
This section establishes the canonical game specification for Orbit Wars: a 2- or 4-player real-time strategy game played on a 100x100 continuous 2D space with a central sun (line 17, line 21). It is the implementer's source of truth for board geometry, planet/fleet/comet representation, the seven-phase turn loop, fleet-speed kinematics, combat resolution, termination conditions, the observation schema, the action format, and the configuration parameters exposed by the Kaggle environment. An agent author should be able to derive a complete world model and a valid `agent(obs)` function from this section alone.

## Methods

**State space (lines 23-99):**
- **Board** (line 25): 100x100 continuous space, origin at top-left.
- **Sun** (line 26): centered at (50, 50), radius 10. Fleets crossing the sun are destroyed.
- **Symmetry rule** (line 27): all planets and comets placed with 4-fold mirror symmetry around the center: `(x, y), (100-x, y), (x, 100-y), (100-x, 100-y)`. Ensures starting-position fairness.
- **Planet record** (line 31): `[id, owner, x, y, radius, ships, production]`.
  - `owner` (line 33): Player ID 0-3, or `-1` for neutral.
  - `radius` (line 34): derived from production, `1 + ln(production)`.
  - `production` (line 35): integer 1-5; each turn an owned planet generates this many ships.
  - `ships` (line 36): current garrison; starts between 5 and 99 (skewed low).
- **Planet types** (lines 40-42):
  - **Orbiting**: `orbital_radius + planet_radius < 50` rotate around sun at constant angular velocity 0.025-0.05 rad/turn (randomized per game). Predict via `initial_planets` + `angular_velocity`.
  - **Static**: planets further from center do not rotate.
- **Map composition** (line 43): 20-40 planets = 5-10 symmetric groups of 4. ≥3 groups guaranteed static, ≥1 group guaranteed orbiting.
- **Home planets** (line 47): one symmetric group randomly chosen as starts. 2-player: diagonally opposite (Q1 and Q4). 4-player: one each. Home planets start with 10 ships.
- **Fleet record** (line 51): `[id, owner, x, y, angle, from_planet_id, ships]`. `angle` in radians (line 53); `ships` does not change during travel (line 54).
- **Comets** (lines 89-99):
  - Spawn in groups of 4 (one per quadrant) at steps 50, 150, 250, 350, 450 (line 89).
  - Radius 1.0 fixed (line 91). Production 1 ship/turn when owned (line 92).
  - Starting ships: minimum of 4 rolls from 1-99; all 4 comets in a group share the same count (line 93).
  - Speed = `cometSpeed`, default 4.0 units/turn (line 94).
  - `comet_planet_ids` lists IDs that are comets; comets ALSO appear in `planets` and follow normal rules — capture, production, fleet launch, combat (line 95).
  - When a comet leaves the board, it is removed along with garrisoned ships (line 97).
  - Comets are removed BEFORE fleet launches each turn — cannot launch from a departing comet (line 97).
  - `comets` field includes `paths` (full trajectory) and `path_index` (current position) for prediction (line 99).

**Action space (lines 80-85, 148-158):**
- Each action: `[from_planet_id, direction_angle, num_ships]`.
- Must own source planet (line 81); cannot exceed garrison (line 82); fleet spawns just outside planet radius in given direction (line 83); multiple launches per turn allowed (line 85).
- Empty list `[]` = no action (line 158).
- `direction_angle`: 0 = right, pi/2 = down (line 155).

**Dynamics — Turn order (7 phases, lines 103-111):**
1. Comet expiration — remove comets that have left the board.
2. Comet spawning — spawn new groups at designated steps.
3. Fleet launch — process all player actions, create fleets.
4. Production — all owned planets (including comets) generate ships.
5. Fleet movement — move fleets along headings; check out-of-bounds, sun, planet collisions; planet-collisions queued for combat.
6. Planet rotation & comet movement — orbiting planets rotate; comets advance; any fleet swept by a moving planet/comet is queued into combat with it.
7. Combat resolution — resolve all queued planet combats.

**Fleet kinematics (lines 60-66, 70-76):**
- `speed = 1.0 + (maxSpeed - 1.0) * (log(ships) / log(1000)) ^ 1.5` (line 61).
- 1 ship = 1.0/turn; ~500 ships ≈ 5; ~1000 ships = max (default 6.0) (lines 64-66).
- Removal triggers (lines 70-74): out of bounds; segment within sun radius; segment within any planet radius (triggers combat).
- Continuous (swept) collision detection — entire path segment from old to new position is checked (line 76).

**Combat resolution (lines 113-122):**
1. Group arriving fleets by owner; sum same-owner ships (line 117).
2. Largest force fights second-largest; difference survives (line 118).
3. If a survivor exists:
   - Same owner as planet → join garrison (line 120).
   - Different owner → fight garrison; if attackers exceed garrison, ownership flips and the surplus becomes the new garrison (line 121).
4. If two attackers tie → all attacking ships destroyed, no survivors (line 122).

**Scoring & termination (lines 126-131):**
- 500-turn step limit (line 128) OR only one (or zero) player remains with any planets/fleets (line 129).
- Final score = total ships on owned planets + total ships in owned fleets; highest wins (line 131).

## Numerical params / hyperparams

**Configuration table (lines 180-187):**
- `episodeSteps` = 500 (max turns)
- `actTimeout` = 1 (seconds per turn)
- `shipSpeed` = 6.0 (max fleet speed)
- `sunRadius` = 10.0
- `boardSize` = 100.0
- `cometSpeed` = 4.0 units/turn

**Other constants embedded in prose:**
- Sun center: (50, 50) (line 26).
- Production range per planet: integer 1-5 (line 35).
- Garrison starting range: 5-99, skewed low (line 36).
- Home-planet starting ships: 10 (line 47).
- Angular velocity range (orbiting): 0.025-0.05 rad/turn, per-game randomized (line 40).
- Orbital classification threshold: `orbital_radius + planet_radius < 50` (line 40); implies `ROTATION_RADIUS_LIMIT = 50` (imported constant, line 165).
- Planet count: 20-40 (5-10 symmetric groups of 4) (line 43).
- Static-group guarantee ≥3; orbiting-group guarantee ≥1 (line 43).
- Comet radius: 1.0 fixed (line 91).
- Comet production: 1/turn (line 92).
- Comet starting ships: min of 4 rolls from 1-99, shared across the 4-comet group (line 93).
- Comet spawn turns: 50, 150, 250, 350, 450 (line 89).
- Fleet-speed exponent: 1.5; log-base immaterial via change-of-base (line 61).
- Speed waypoints: 1 ship → 1.0; ~500 → ~5; ~1000 → max (lines 64-66).
- Player IDs: 0-3 (line 33, line 139). Neutral owner: -1 (line 33).
- Planet radius formula: `1 + ln(production)` (line 34).

## Reusable code patterns

Example agent code (lines 164-176) — verbatim:

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

Key patterns:
- Import `Planet`, `Fleet`, `CENTER`, `ROTATION_RADIUS_LIMIT` from `kaggle_environments.envs.orbit_wars.orbit_wars` (line 165).
- Splat list rows into named tuples: `Planet(*p)`, `Fleet(*f)` (lines 169-170).
- `obs` is dict-like: `obs.get(key, default)` (lines 169-171).
- Action shape: `list[[from_planet_id, angle, num_ships]]`; empty list = pass (line 175, line 158).

## Reported leaderboard score
n/a

## Anything novel worth replicating

- **Predictive trajectory model**: `initial_planets` + `angular_velocity` give exact future positions of orbiting planets at any t (deterministic constant rotation) (line 40, line 141). Strong basis for ballistic targeting.
- **Comet path lookahead**: `comets[i].paths` + `path_index` enables full-lifetime comet position prediction (line 99, line 142).
- **Comet ID aliasing**: comets are in BOTH `planets` and `comet_planet_ids` — must filter to avoid treating ephemeral comets as durable territory (line 95, line 143). Garrisoned ships vanish on expiration (line 97).
- **Pre-launch comet expiration**: phase 1 runs before phase 3, so a launch from a departing comet is silently dropped (line 97, lines 105-107).
- **Continuous collision detection**: prevents fleet "tunneling" through the sun or planets (line 76).
- **Phase-6 sweep-up**: stationary fleets can be caught by orbiting planets and dragged into combat (line 110).
- **Logarithmic speed curve**: huge fleets only marginally faster than mid-size; stacking-for-speed has a sharp ceiling (line 61, line 66).
- **Tie destruction**: equal attackers annihilate before defender rolls — usable for sacrificial denial (line 122).
- **Same-owner reinforcement**: friendly fleets joining own planet during combat tick add to garrison even amid other attackers (line 120).
- **Symmetry-aware seed parity**: 4-fold symmetry → strategic patterns are quadrant-rotatable.

## Direct quotes / code snippets to preserve

**Turn order (lines 103-111):**
> Each turn executes in this order:
> 1. Comet expiration: Remove comets that have left the board.
> 2. Comet spawning: Spawn new comet groups at designated steps.
> 3. Fleet launch: Process all player actions, creating new fleets.
> 4. Production: All owned planets (including comets) generate ships.
> 5. Fleet movement: Move all fleets along their headings. Check for out-of-bounds, sun collision, and planet collision. Fleets that hit planets are queued for combat.
> 6. Planet rotation & comet movement: Orbiting planets rotate, comets advance along their paths. Any fleet caught by a moving planet/comet is swept into combat with it.
> 7. Combat resolution: Resolve all queued planet combats.

**Combat resolution (lines 115-122):**
> When one or more fleets collide with a planet (either by flying into it or being swept by a moving planet), combat is resolved:
> 1. All arriving fleets are grouped by owner. Ships from the same owner are summed.
> 2. The largest attacking force fights the second largest. The difference in ships survives.
> 3. If there is a surviving attacker:
>    - If the attacker is the same owner as the planet, the surviving ships are added to the garrison.
>    - If the attacker is a different owner, the surviving ships fight the garrison. If the attackers exceed the garrison, the planet changes ownership and the garrison becomes the surplus.
> 4. If two attackers tie, all attacking ships are destroyed (no survivors).

**Fleet-speed formula (line 61):**
```
speed = 1.0 + (maxSpeed - 1.0) * (log(ships) / log(1000)) ^ 1.5
```

**Observation reference (lines 135-144):**

| Field | Type | Description |
|-------|------|-------------|
| `planets` | `[[id, owner, x, y, radius, ships, production], ...]` | All planets including comets |
| `fleets` | `[[id, owner, x, y, angle, from_planet_id, ships], ...]` | All active fleets |
| `player` | `int` | Your player ID (0-3) |
| `angular_velocity` | `float` | Planet rotation speed (radians/turn) |
| `initial_planets` | `[[id, owner, x, y, radius, ships, production], ...]` | Planet positions at game start |
| `comets` | `[{planet_ids, paths, path_index}, ...]` | Active comet group data |
| `comet_planet_ids` | `[int, ...]` | Planet IDs that are comets |
| `remainingOverageTime` | `float` | Remaining overage time budget (seconds) |

**Action format (lines 150-152):**
```python
[[from_planet_id, direction_angle, num_ships], ...]
```

**Symmetry rule (line 27):**
> All planets and comets are placed with 4-fold mirror symmetry around the center: (x, y), (100-x, y), (x, 100-y), (100-x, 100-y).

**Orbiting classification (line 40):**
> Planets whose `orbital_radius + planet_radius < 50` rotate around the sun at a constant angular velocity (0.025-0.05 radians/turn, randomized per game).

## Open questions / things I couldn't determine

- **Tie behavior with 3+ attackers**: line 118 says "largest fights second-largest"; line 122 says "if two attackers tie, all attacking ships are destroyed." Behavior with three-way ties or when 1st and 2nd tie but a smaller 3rd exists is unspecified.
- **Comet starting-ship distribution**: "minimum of 4 rolls from 1-99" (line 93) — distribution of each "roll" (uniform integer?) not made explicit.
- **`remainingOverageTime` semantics**: listed (line 144) but not described — accounting (per-turn vs cumulative, refresh policy) unspecified.
- **Fleet ID reuse / Planet ID reuse for expired comets**: not stated whether IDs are unique across the game or recycled.
- **Spawn position offset**: "just outside the planet's radius" (line 83) — exact offset not specified.
- **Movement order within phases 5/6**: deterministic ordering for multiple fleets / multiple orbital planets, and resolution of simultaneous arrivals, not specified.
- **Action validation on illegal moves**: behavior for over-budget `num_ships`, non-owned `from_planet_id`, or invalid angles not stated (drop / clamp / error).
- **Relationship between `actTimeout = 1` and `remainingOverageTime`**: hard limit vs soft buffer not made explicit here.
- **Production timing on freshly captured planets**: phase 4 (production) runs before phase 7 (combat resolution) — a planet whose ownership flips in phase 7 has already produced for its old owner. Logically deducible but not stated outright (lines 103-111).
- **Production on freshly spawned comets**: phase 2 precedes phase 4 — newly spawned comets are presumably ownerless/neutral on spawn turn so they don't produce, but not stated.
- **`CENTER` constant value**: imported on line 165 but never explicitly defined; clearly `(50, 50)` from line 26.
- **Logarithm base in speed formula**: `log(ships)/log(1000)` is base-invariant (cancels via change-of-base) — unambiguous, but worth flagging for implementers.
