# E6: pilkwang-structured-baseline

## Source
https://www.kaggle.com/code/pilkwang/orbit-wars-structured-baseline

## Fetch method
WebFetch — `kaggle kernels pull` was sandbox-blocked, the public `/code/...` URL renders only a title, and the `Write` tool was also denied (so the file at the requested OUTPUT FILE path could not be created; report is delivered inline). The internal endpoint `https://www.kaggle.com/api/v1/kernels/pull?userName=pilkwang&kernelSlug=orbit-wars-structured-baseline` returned full notebook content via WebFetch. Cell numbering below is from that response and may be off-by-one if Kaggle's UI re-numbers, but the code groupings are stable.

## Goal
Build a fully heuristic, deterministic, single-file `submission.py` agent that decides each turn through a 5-layer pipeline: legal shot → future-state forecast → hold/rescue/recapture → mission ranking (capture / snipe / swarm / crash exploit / reinforce / followup) → commit loop with re-aim. Every decision is anchored to **arrival-time ownership**: query projected garrison/owner at the actual ETA accounting for in-flight fleets, production, and same-turn combat — not the snapshot. The notebook self-titles "v11" and is a structured-but-pure-heuristic baseline (no ML). Author acknowledges it is strong in 1v1 but vulnerable to 1-vs-3 dogpile situations.

## Methods

### Module decomposition (cell-by-cell)
| Cell | Type | Content |
|------|------|---------|
| 1 | Markdown | Title, "v11" subtitle |
| 2 | HTML | Visual 5-layer system map |
| 3 | Markdown | Decision-flow table |
| 4 | Python | `kaggle-environments>=1.28.0` upgrade gate |
| 5 | Markdown | Setup description |
| 6 | Python | Constants + `Planet`/`Fleet` namedtuples + `ShotOption`/`Mission` dataclasses (header of `submission.py`) |
| 7 | Python | Physics layer (geometry, sun avoidance, `fleet_speed`, position prediction, `aim_with_prediction`) |
| 8 | Python | World model (`build_arrival_ledger`, `resolve_arrival_event`, `simulate_planet_timeline`, `WorldModel` with `min_ships_to_own_at`, `reinforcement_needed_to_hold_until`) |
| 9 | Python | Strategy (`build_policy_state`, `build_modes`, `settle_plan`, mission builders, `target_value`, `apply_score_modifiers`, `preferred_send`, `opening_filter`, `detect_enemy_crashes`) |
| 10 | Python | `agent(observation)` entry point |

The notebook writes one monolithic `submission.py` (~196 KB), standard-library only, deterministic.

### Decision pipeline (5 layers)

1. **Legal shot (Cell 7)** — `aim_with_prediction(src, target, ships, ...)` validates a single straight launch is sun-safe (`segment_hits_sun` rejects any line within `SUN_R + SUN_SAFETY = 11.5` of center) and computes ETA from `fleet_speed(ships)`. For moving targets it iterates up to 5 times to converge on a self-consistent intercept (delta < `INTERCEPT_TOLERANCE = 1` turn). Falls back to `search_safe_intercept` (scans candidate arrival turns within `ROUTE_SEARCH_HORIZON = 60`) if direct line is sun-blocked. `comet_remaining_life` caps comet intercepts.

2. **Future state (Cell 8)** — `WorldModel` precomputes `simulate_planet_timeline` over `HORIZON = 110`. Per turn: add production if owned, then resolve same-turn combat via `resolve_arrival_event` (aggregate ships per owner → top two cancel → survivor fights garrison). Outputs `owner_at[t]`, `ships_at[t]`, `keep_needed` (binary search for minimum garrison that survives), `min_owned`, `first_enemy`, `fall_turn`, `holds_full`. `min_ships_to_own_by(target, eval_turn, attacker)` uses exponential-then-binary search calling `projected_state` (replays timeline with hypothetical extra arrivals + planned commitments) → exact ownership threshold including same-turn interactions.

3. **Hold logic (Cell 9)** — three separate defense missions:
   - **Reinforce**: pre-emptive top-up via `reinforcement_needed_to_hold_until` (REINFORCE_HOLD_LOOKAHEAD = 20).
   - **Rescue**: emergency, anchored at `fall_turn` (DEFENSE_LOOKAHEAD_TURNS = 28). `eval_turn_fn` always returns `fall_turn`.
   - **Recapture**: counter-attack, RECAPTURE_LOOKAHEAD_TURNS = 10.

4. **Mission layer (Cell 9)**:
   - **Capture** through `opening_filter`.
   - **Snipe** anchored at enemy ETA.
   - **Swarm** with `MULTI_SOURCE_TOP_K = 5`, `MULTI_SOURCE_ETA_TOLERANCE = 2`; 3-source variant gated by `THREE_SOURCE_MIN_TARGET_SHIPS = 20`.
   - **Crash exploit** (4-player only): `detect_enemy_crashes` finds two different-owner enemy arrivals at the same planet within `CRASH_EXPLOIT_ETA_WINDOW = 2`; mop-up timed `+1` turn after crash.
   - **Followup / rear staging** for late-game flow.

5. **Commit loop (Cell 10 → `plan_moves`)** — accept missions in score order; update `planned_commitments` so subsequent `min_ships_to_own_by` calls see new arrivals; re-aim leftovers; doomed-evac (`DOOMED_EVAC_TURN_LIMIT = 24`); rear staging.

### `settle_plan` — fleet-size/speed self-consistency
Because `fleet_speed = 1 + 5*(log(ships)/log(1000))^1.5`, send size affects ETA, which affects `need`, which may change desired send. Iterates up to `max_iter = 4` times moving toward `desired`; preserves the previously-tested legal fallback so it never returns infeasible.

### Strategic mode flags
```
domination = (my_total - enemy_total) / max(1, my_total + enemy_total)
is_behind     = domination < -0.20
is_ahead      = domination >  0.18
is_finishing  = domination >  0.35  AND  my_prod > enemy_prod*1.25  AND  step > 100
is_dominating = is_ahead OR my_total > max_enemy*1.25
```
Drives `attack_margin_mult` (±0.05–0.08) and value multipliers.

### Reaction-time gating
`reaction_time_map[target] = (my_min_eta, enemy_min_eta)` over the top-4 nearest sources each. `reaction_gap = enemy_t - my_t` drives opening filter and proactive defense.

### Proactive reserve / attack budget
`reserve = max(keep_needed, proactive_keep)`, `attack_budget = ships - reserve`. `proactive_keep` looks at top-3 nearest enemies and reserves ≥18% of incoming garrison projected within PROACTIVE_DEFENSE_HORIZON = 12; multi-enemy stacking adds 22% within 14 turns when ≥2 stack.

## Numerical params / hyperparams

### Board / physics
- `BOARD = 100.0`; `CENTER_X = CENTER_Y = 50.0`
- `SUN_R = 10.0`, `SUN_SAFETY = 1.5` (reject within 11.5 of center)
- `MAX_SPEED = 6.0`, `LAUNCH_CLEARANCE = 0.1`
- `ROTATION_LIMIT = 50.0` (static if `r_orb + r_planet ≥ 50`)
- `TOTAL_STEPS = 500`; `SIM_HORIZON = HORIZON = 110`; `ROUTE_SEARCH_HORIZON = 60`
- `INTERCEPT_TOLERANCE = 1`; `COMET_MAX_CHASE_TURNS = 10`
- Speed law: `1.0 + 5.0 * (log(ships)/log(1000))^1.5`

### Time-phase
- `EARLY_TURN_LIMIT = 40`, `OPENING_TURN_LIMIT = 80`
- `LATE_REMAINING_TURNS = 60`, `VERY_LATE_REMAINING_TURNS = 25`
- `LATE_CAPTURE_BUFFER = 5`, `VERY_LATE_CAPTURE_BUFFER = 3`

### Cost weights (denominator: `value / (send + turns*cost_w + 1)`)
- `ATTACK_COST_TURN_WEIGHT = 0.55`, `SNIPE_COST_TURN_WEIGHT = 0.45`, `DEFENSE_COST_TURN_WEIGHT = 0.40`, `RECAPTURE_COST_TURN_WEIGHT = 0.52`, `REINFORCE_COST_TURN_WEIGHT = 0.35`

### Value multipliers (`target_value`)
- Static neutral 1.4, static hostile 1.55, rotating-during-opening 0.9
- Hostile target 1.85 (opening 1.45)
- Safe neutral 1.2, contested neutral 0.7, early neutral 1.2
- Comet 0.65; snipe 1.12; swarm 1.05; reinforce 1.35; crash-exploit 1.18
- Finishing-hostile 1.15; behind-rotating-neutral 0.92; behind+safe-neutral ×1.08; dominating+contested-neutral ×0.92

### Score multipliers (post-cost-ratio, `apply_score_modifiers`)
- Static target 1.18; early-static-neutral 1.25
- 4p rotating-neutral 0.84; dense-static-cluster (≥4) → rotating-neutral ×0.86
- Snipe 1.12, swarm 1.06, crash-exploit 1.05

### Margin / send sizing (`preferred_send`)
- Neutral: `min(8, 2 + prod*2)`; Hostile: `min(12, 3 + prod*2)`
- +4 static, +5 contested neutral, +3 four-player
- Long travel: `+min(8, turns//3)` once `turns > 18`
- Comet relief −6; finishing-hostile +3

### Indirect wealth
- `INDIRECT_VALUE_SCALE = 0.15` applied as `indirect * turns_profit * 0.15`
- Per-neighbor weights: friendly 0.35, neutral 0.9, enemy 1.25

### Domination thresholds
- `BEHIND_DOMINATION = -0.20`, `AHEAD_DOMINATION = 0.18`, `FINISHING_DOMINATION = 0.35`, `FINISHING_PROD_RATIO = 1.25`
- `AHEAD_ATTACK_MARGIN_BONUS = 0.08`, `BEHIND_ATTACK_MARGIN_PENALTY = 0.05`, `FINISHING_ATTACK_MARGIN_BONUS = 0.08`

### Defense / reinforce / recapture
- `DEFENSE_LOOKAHEAD_TURNS = 28`; `DEFENSE_FRONTIER_SCORE_MULT = 1.12` (nearest enemy < 22)
- `DEFENSE_SHIP_VALUE = 0.55`; `DEFENSE_SEND_MARGIN_BASE = 1`, `DEFENSE_SEND_MARGIN_PROD_WEIGHT = 1`
- `REINFORCE_MIN_PRODUCTION = 2`, `REINFORCE_MAX_TRAVEL_TURNS = 22`, `REINFORCE_SAFETY_MARGIN = 2`, `REINFORCE_MAX_SOURCE_FRACTION = 0.75`, `REINFORCE_MIN_FUTURE_TURNS = 40`, `REINFORCE_HOLD_LOOKAHEAD = 20`
- `RECAPTURE_LOOKAHEAD_TURNS = 10`, `RECAPTURE_VALUE_MULT = 0.88`, `RECAPTURE_FRONTIER_MULT = 1.08`, `RECAPTURE_PRODUCTION_WEIGHT = 0.6`, `RECAPTURE_IMMEDIATE_WEIGHT = 0.4`
- `DOOMED_EVAC_TURN_LIMIT = 24`, `DOOMED_MIN_SHIPS = 8`

### Proactive defense
- `PROACTIVE_DEFENSE_HORIZON = 12`, `PROACTIVE_DEFENSE_RATIO = 0.18`
- `MULTI_ENEMY_PROACTIVE_HORIZON = 14`, `MULTI_ENEMY_PROACTIVE_RATIO = 0.22`, `MULTI_ENEMY_STACK_WINDOW = 3`
- `REACTION_SOURCE_TOP_K_MY = REACTION_SOURCE_TOP_K_ENEMY = 4`, `PROACTIVE_ENEMY_TOP_K = 3`

### Coordination
- `PARTIAL_SOURCE_MIN_SHIPS = 6`; `MULTI_SOURCE_TOP_K = 5`, `MULTI_SOURCE_ETA_TOLERANCE = 2`, `MULTI_SOURCE_PLAN_PENALTY = 0.97`
- `HOSTILE_SWARM_ETA_TOLERANCE = 1`
- `THREE_SOURCE_SWARM_ENABLED = True`, `THREE_SOURCE_MIN_TARGET_SHIPS = 20`, `THREE_SOURCE_ETA_TOLERANCE = 1`, `THREE_SOURCE_PLAN_PENALTY = 0.93`
- `FOLLOWUP_MIN_SHIPS = 8`

### Crash exploit (4-player only)
- `CRASH_EXPLOIT_ENABLED = True`, `CRASH_EXPLOIT_MIN_TOTAL_SHIPS = 10`, `CRASH_EXPLOIT_ETA_WINDOW = 2`, `CRASH_EXPLOIT_POST_CRASH_DELAY = 1`

### Opening filter
- `SAFE_OPENING_PROD_THRESHOLD = 4`, `SAFE_OPENING_TURN_LIMIT = 10`
- `ROTATING_OPENING_MAX_TURNS = 13`, `ROTATING_OPENING_LOW_PROD = 2`
- `FOUR_PLAYER_ROTATING_REACTION_GAP = 3`, `FOUR_PLAYER_ROTATING_SEND_RATIO = 0.62`, `FOUR_PLAYER_ROTATING_TURN_LIMIT = 10`
- `SAFE_NEUTRAL_MARGIN = 2`, `CONTESTED_NEUTRAL_MARGIN = 2`

### Late game
- `LATE_IMMEDIATE_SHIP_VALUE = 0.6`, `WEAK_ENEMY_THRESHOLD = 45`, `ELIMINATION_BONUS = 18.0`

### Rear staging
- `REAR_SOURCE_MIN_SHIPS = 16`, `REAR_DISTANCE_RATIO = 1.25`, `REAR_STAGE_PROGRESS = 0.78`
- `REAR_SEND_RATIO_TWO_PLAYER = 0.62`, `REAR_SEND_RATIO_FOUR_PLAYER = 0.7`
- `REAR_SEND_MIN_SHIPS = 10`, `REAR_MAX_TRAVEL_TURNS = 40`

### Time budget
- `SOFT_ACT_DEADLINE = 0.82` (act with 82% of `max_time`)
- `HEAVY_PHASE_MIN_TIME = 0.16`, `OPTIONAL_PHASE_MIN_TIME = 0.08`
- `HEAVY_ROUTE_PLANET_LIMIT = 32`

## Reusable code patterns

### State parsing (Cell 10)
```python
Planet = namedtuple("Planet", ["id","owner","x","y","radius","ships","production"])
Fleet  = namedtuple("Fleet",  ["id","owner","x","y","angle","from_planet_id","ships"])

planets = [Planet(id=p["id"], owner=p["owner"], x=p["x"], y=p["y"],
                  radius=p["r"], ships=p["ship_count"], production=p["production"])
           for p in observation.game_state.planets]
fleets  = [Fleet(id=f["id"], owner=f["owner"], x=f["x"], y=f["y"],
                 angle=f["dx"], from_planet_id=f["c"], ships=f["ship_count"])
           for f in observation.game_state.fleets]
```
Note unusual mapping: fleet `dx` interpreted as angle, `c` as `from_planet_id` — verify against env schema before adopting verbatim.

### Geometry helpers (Cell 7)
```python
def dist(ax, ay, bx, by): return math.hypot(ax-bx, ay-by)

def orbital_radius(planet): return dist(planet.x, planet.y, CENTER_X, CENTER_Y)

def is_static_planet(planet):
    return orbital_radius(planet) + planet.radius >= ROTATION_LIMIT

def fleet_speed(ships):
    if ships <= 1: return 1.0
    ratio = max(0.0, min(1.0, math.log(ships)/math.log(1000.0)))
    return 1.0 + (MAX_SPEED - 1.0) * (ratio**1.5)

def point_to_segment_distance(px, py, x1, y1, x2, y2):
    dx, dy = x2-x1, y2-y1
    seg = dx*dx + dy*dy
    if seg <= 1e-9: return dist(px, py, x1, y1)
    t = max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy) / seg))
    return dist(px, py, x1+t*dx, y1+t*dy)

def segment_hits_sun(x1, y1, x2, y2, safety=SUN_SAFETY):
    return point_to_segment_distance(CENTER_X, CENTER_Y, x1, y1, x2, y2) < SUN_R + safety

def safe_angle_and_distance(sx, sy, sr, tx, ty, tr):
    angle = math.atan2(ty-sy, tx-sx)
    start_x = sx + math.cos(angle)*(sr + LAUNCH_CLEARANCE)
    start_y = sy + math.sin(angle)*(sr + LAUNCH_CLEARANCE)
    hit_d = max(0.0, dist(sx,sy,tx,ty) - (sr + LAUNCH_CLEARANCE) - tr)
    end_x = start_x + math.cos(angle)*hit_d
    end_y = start_y + math.sin(angle)*hit_d
    if segment_hits_sun(start_x, start_y, end_x, end_y): return None
    return angle, hit_d
```
Adopt verbatim — these are tight and correct.

### Same-turn combat (Cell 8)
```python
def resolve_arrival_event(owner, garrison, arrivals):
    by_owner = {}
    for _, attacker_owner, ships in arrivals:
        by_owner[attacker_owner] = by_owner.get(attacker_owner, 0) + ships
    if not by_owner: return owner, max(0.0, garrison)
    s = sorted(by_owner.items(), key=lambda kv: kv[1], reverse=True)
    top_owner, top_ships = s[0]
    if len(s) > 1:
        second = s[1][1]
        if top_ships == second:
            survivor_owner, survivor_ships = -1, 0  # mutual annihilation
        else:
            survivor_owner, survivor_ships = top_owner, top_ships - second
    else:
        survivor_owner, survivor_ships = top_owner, top_ships
    if survivor_ships <= 0: return owner, max(0.0, garrison)
    if owner == survivor_owner: return owner, garrison + survivor_ships
    garrison -= survivor_ships
    if garrison < 0: return survivor_owner, -garrison
    return owner, garrison
```
**Critical fidelity anchor — replicate exactly.**

### Iterative intercept (Cell 7)
```python
def aim_with_prediction(src, target, ships, initial_by_id, ang_vel, comets, comet_ids):
    est = estimate_arrival(src.x, src.y, src.radius, target.x, target.y, target.radius, ships)
    if est is None:
        if not target_can_move(target, initial_by_id, comet_ids): return None
        return search_safe_intercept(src, target, ships, initial_by_id, ang_vel, comets, comet_ids)
    tx, ty = target.x, target.y
    for _ in range(5):
        _, turns = est
        pos = predict_target_position(target, turns, initial_by_id, ang_vel, comets, comet_ids)
        if pos is None: return None
        ntx, nty = pos
        next_est = estimate_arrival(src.x, src.y, src.radius, ntx, nty, target.radius, ships)
        if next_est is None:
            return search_safe_intercept(...) if target_can_move(...) else None
        if abs(ntx-tx) < 0.3 and abs(nty-ty) < 0.3 and abs(next_est[1]-turns) <= INTERCEPT_TOLERANCE:
            return next_est[0], next_est[1], ntx, nty
        tx, ty = ntx, nty; est = next_est
    final = estimate_arrival(src.x, src.y, src.radius, tx, ty, target.radius, ships)
    return None if final is None else (final[0], final[1], tx, ty)
```

### `min_ships_to_own_by` (Cell 8) — exact-need binary search
```python
def min_ships_to_own_by(self, target_id, eval_turn, attacker_owner,
                       arrival_turn=None, planned_commitments=None,
                       extra_arrivals=(), upper_bound=None):
    owner_before, ships_before = self.projected_state(
        target_id, eval_turn,
        planned_commitments=planned_commitments,
        extra_arrivals=normalized_extra)
    if owner_before == attacker_owner: return 0

    def owns_at(ships):
        owner_after, _ = self.projected_state(
            target_id, eval_turn,
            planned_commitments=planned_commitments,
            extra_arrivals=normalized_extra + ((arrival_turn, attacker_owner, int(ships)),))
        return owner_after == attacker_owner

    hi = upper_bound or max(1, int(math.ceil(ships_before)) + 1)
    while hi <= self._ownership_search_cap(eval_turn) and not owns_at(hi):
        hi *= 2
    lo = 1
    while lo < hi:
        mid = (lo + hi) // 2
        if owns_at(mid): hi = mid
        else:            lo = mid + 1
    return lo
```

### Crash detection (Cell 9)
```python
def detect_enemy_crashes(world):
    crashes = []
    for target_id, arrivals in world.arrivals_by_planet.items():
        events = sorted([(int(math.ceil(eta)), o, int(s))
                         for eta, o, s in arrivals
                         if o not in (-1, world.player) and s > 0])
        for i in range(len(events)):
            eta_a, owner_a, ships_a = events[i]
            for j in range(i+1, len(events)):
                eta_b, owner_b, ships_b = events[j]
                if owner_a == owner_b: continue
                if abs(eta_a - eta_b) > CRASH_EXPLOIT_ETA_WINDOW: break
                if ships_a + ships_b < CRASH_EXPLOIT_MIN_TOTAL_SHIPS: continue
                crashes.append({"target_id": target_id, "crash_turn": max(eta_a, eta_b),
                                "owners": (owner_a, owner_b), "ships": (ships_a, ships_b)})
    return crashes
```

### `target_value` (Cell 9) — master scoring
```python
def target_value(target, arrival_turns, mission, world, modes, policy):
    turns_profit = max(1, world.remaining_steps - arrival_turns)
    if target.id in world.comet_ids:
        life = world.comet_life(target.id)
        turns_profit = max(0, min(turns_profit, life - arrival_turns))
        if turns_profit <= 0: return -1.0
    value  = target.production * turns_profit
    value += policy["indirect_wealth_map"][target.id] * turns_profit * INDIRECT_VALUE_SCALE
    if world.is_static(target.id):
        value *= STATIC_NEUTRAL_VALUE_MULT if target.owner == -1 else STATIC_HOSTILE_VALUE_MULT
    else:
        value *= ROTATING_OPENING_VALUE_MULT if world.is_opening else 1.0
    if target.owner not in (-1, world.player):
        value *= OPENING_HOSTILE_TARGET_VALUE_MULT if world.is_opening else HOSTILE_TARGET_VALUE_MULT
    if target.owner == -1:
        if   is_safe_neutral(target, policy):      value *= SAFE_NEUTRAL_VALUE_MULT
        elif is_contested_neutral(target, policy): value *= CONTESTED_NEUTRAL_VALUE_MULT
        if world.is_early: value *= EARLY_NEUTRAL_VALUE_MULT
    if target.id in world.comet_ids: value *= COMET_VALUE_MULT
    if   mission == "snipe":         value *= SNIPE_VALUE_MULT
    elif mission == "swarm":         value *= SWARM_VALUE_MULT
    elif mission == "reinforce":     value *= REINFORCE_VALUE_MULT
    elif mission == "crash_exploit": value *= CRASH_EXPLOIT_VALUE_MULT
    if world.is_late:
        value += max(0, target.ships) * LATE_IMMEDIATE_SHIP_VALUE
        if target.owner not in (-1, world.player) and \
           world.owner_strength.get(target.owner, 0) <= WEAK_ENEMY_THRESHOLD:
            value += ELIMINATION_BONUS
    if modes["is_finishing"] and target.owner not in (-1, world.player):
        value *= FINISHING_HOSTILE_VALUE_MULT
    if modes["is_behind"] and target.owner == -1 and not world.is_static(target.id):
        value *= BEHIND_ROTATING_NEUTRAL_VALUE_MULT
    if modes["is_behind"] and target.owner == -1 and is_safe_neutral(target, policy):
        value *= 1.08
    if modes["is_dominating"] and target.owner == -1 and is_contested_neutral(target, policy):
        value *= 0.92
    return value
```

### `preferred_send` (Cell 9)
```python
def preferred_send(target, base_needed, arrival_turns, src_available, world, modes, policy):
    send = max(base_needed, int(math.ceil(base_needed * modes["attack_margin_mult"])))
    margin = 0
    if target.owner == -1:
        margin += min(NEUTRAL_MARGIN_CAP, NEUTRAL_MARGIN_BASE + target.production*NEUTRAL_MARGIN_PROD_WEIGHT)
    else:
        margin += min(HOSTILE_MARGIN_CAP, HOSTILE_MARGIN_BASE + target.production*HOSTILE_MARGIN_PROD_WEIGHT)
    if world.is_static(target.id):           margin += STATIC_TARGET_MARGIN
    if is_contested_neutral(target, policy): margin += CONTESTED_TARGET_MARGIN
    if world.is_four_player:                 margin += FOUR_PLAYER_TARGET_MARGIN
    if arrival_turns > LONG_TRAVEL_MARGIN_START:
        margin += min(LONG_TRAVEL_MARGIN_CAP, arrival_turns // LONG_TRAVEL_MARGIN_DIVISOR)
    if target.id in world.comet_ids:         margin = max(0, margin - COMET_MARGIN_RELIEF)
    if modes["is_finishing"] and target.owner not in (-1, world.player):
        margin += FINISHING_HOSTILE_SEND_BONUS
    return min(src_available, send + margin)
```

### `opening_filter` (Cell 9)
```python
def opening_filter(target, arrival_turns, needed, src_available, world, policy):
    if not world.is_opening or target.owner != -1: return False
    if target.id in world.comet_ids:               return False
    if world.is_static(target.id):                 return False
    my_t, enemy_t = policy_reaction_times(target.id, policy)
    reaction_gap = enemy_t - my_t
    if (target.production >= SAFE_OPENING_PROD_THRESHOLD
            and arrival_turns <= SAFE_OPENING_TURN_LIMIT
            and reaction_gap >= SAFE_NEUTRAL_MARGIN):
        return False
    if world.is_four_player:
        affordable = needed <= max(PARTIAL_SOURCE_MIN_SHIPS,
                                   int(src_available * FOUR_PLAYER_ROTATING_SEND_RATIO))
        if (affordable and arrival_turns <= FOUR_PLAYER_ROTATING_TURN_LIMIT
                and reaction_gap >= FOUR_PLAYER_ROTATING_REACTION_GAP):
            return False
        return True
    return arrival_turns > ROTATING_OPENING_MAX_TURNS or target.production <= ROTATING_OPENING_LOW_PROD
```

## Reported leaderboard score
n/a — no public placement is shown in the notebook (the title and v11 subtitle do not mention rank). Submission output log shows only a self-test `2p vs random: rewards=[1, -1], steps=102` (beat random).

## Anything novel worth replicating

Sorted by perceived value for our v1 heuristic (`src/orbit_wars/heuristic/`):

1. **Arrival-time `min_ships_to_own_at`** — single biggest correctness lever. Properly accounts for production accruing during transit, in-flight visible enemies, and same-turn combat with all other arrivals.
2. **Same-turn combat resolver** matching env semantics (aggregate-by-owner → top-2-cancel → survivor-vs-garrison). Most baselines get this subtly wrong.
3. **`settle_plan` iterative settlement** — handles the speed-vs-size feedback loop (`fleet_speed` makes ETA size-dependent).
4. **5-iteration intercept with sun-safe fallback** for moving targets (rotating planets + comets).
5. **`detect_enemy_crashes`** — cheap to add, free wins in 4-player; trail-by-1-turn force captures the survivor.
6. **Reaction-time gate** (`reaction_time_map[target] = (my_t, enemy_t)`) — drives both opening filter and proactive defense reserves.
7. **Indirect wealth feature** — single scalar per planet from neighbor friendly/neutral/enemy with weights 0.35/0.9/1.25; cheap positional value.
8. **Three separate defense missions** (reinforce / rescue / recapture) with different cost weights and value formulas — collapsing into one bucket loses fidelity.
9. **Time-budget gating** (`SOFT_ACT_DEADLINE = 0.82`, `HEAVY_ROUTE_PLANET_LIMIT = 32`) — cheap TLE insurance.
10. **Probe-with-fallback** in `settle_plan` — always preserve a tested-legal size while iterating.
11. **Domination-mode multipliers** (5–8% adjustments) — prevents over-attacking when winning / under-attacking when losing.
12. **Doomed-evac salvage** — when a planet is forecast to fall, evacuate rather than donate the garrison.
13. **Comet handling**: explicit `comet_remaining_life` cap on intercept search, value × 0.65, margin relief −6.

## Direct quotes / code snippets to preserve

The `target_value`, `preferred_send`, `apply_score_modifiers`, `opening_filter`, `aim_with_prediction`, `resolve_arrival_event`, `min_ships_to_own_by`, and `detect_enemy_crashes` blocks above are the verbatim snippets to preserve in our agent. The constants block (Cells 6 + 9) should be lifted as a single `constants.py` module.

## Open questions / things I couldn't determine

- Exact `plan_moves(world, deadline)` body — the high-level loop calling policy/modes builders, generating all mission types, sorting by score, committing with re-aim. Pull endpoint truncated.
- `WorldModel.projected_timeline` and `projected_state` — described as "replays timeline with planned commitments + extra arrivals" but exact code not returned.
- `WorldModel.indirect_feature_map` construction — distance threshold and per-neighbor weighting policy unclear (likely top-K nearest, but not shown).
- `is_safe_neutral` / `is_contested_neutral` exact predicates — referenced but not dumped. From context: probably `reaction_gap >= SAFE_NEUTRAL_MARGIN` for safe and a symmetric condition for contested.
- Reinforce mission's full scoring formula — multipliers shown but the score expression and accept-vs-defer threshold not in the dump.
- Recapture mission body — only constants listed; `RECAPTURE_PRODUCTION_WEIGHT 0.6 / RECAPTURE_IMMEDIATE_WEIGHT 0.4` blend not shown.
- `Fleet.angle = fleet["dx"]`: literal angle or normalized direction component? Suspicious naming — verify against env's actual fleet schema before adopting.
- Leaderboard placement / public score — none visible.
- Whether REINFORCE is gated by a minimum reaction-time deficit or fires whenever `fall_turn` is in `(DEFENSE_LOOKAHEAD_TURNS, REINFORCE_HOLD_LOOKAHEAD]`.
- `_ownership_search_cap(eval_turn)` exact formula (likely `garrison + production * eval_turn + buffer`).
- Cell numbering may not match the notebook's UI numbering — the API pull groups cells, so a "cell 7" reference here is the seventh logical block in pull order.
