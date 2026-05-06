"""WorldModel: arrival-time ownership forecasting for the heuristic agent.

Lifts E6/E8/E9's structure (synthesis §5.B–§5.C). Every decision in the heuristic
asks "if I send N ships to planet P right now, will P be mine when they arrive?" — that
question requires same-turn combat, in-flight fleets, planet production, and (for
moving targets) iterative intercept resolution. This module provides those pieces.

The :class:`WorldModel` is built fresh each turn from an :class:`ObservationView`. It
caches the per-planet timelines once so the heuristic can issue many forecast queries
cheaply.

Critical invariants from E1/E3:
- Turn order: comet expiration → comet spawn → fleet launch → production → fleet movement → planet rotation/comet movement → combat resolution.
- Same-turn combat: aggregate arrivals by owner, top-2 cancel, survivor fights garrison.
- Two attackers tied → mutual annihilation, garrison untouched.
- Production runs phase 4, before combat — a captured planet still produced for the prior owner this turn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

from .geometry import (
    LAUNCH_CLEARANCE,
    SUN_CENTER,
    SUN_RADIUS,
    SUN_SAFETY,
    dist,
    fleet_speed,
    safe_angle_and_distance,
    swept_pair_hit,
)
from .rotation import predict_planet_position
from .state import Fleet, ObservationView, Planet

__all__ = [
    "ArrivalEvent",
    "DEFAULT_HORIZON",
    "PlanetTimeline",
    "WorldModel",
    "aim_with_prediction",
    "estimate_fleet_eta",
    "path_collision_predicted",
    "predict_target_position",
    "resolve_arrival_event",
]

DEFAULT_HORIZON: int = 110  # E6/E8/E9 default; see synthesis §3.


# ---------------------------------------------------------------------------
# Combat resolution and timeline simulation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArrivalEvent:
    """One fleet arriving at a planet on a specific turn."""

    eta: int  # turn (1-indexed; 1 = next turn)
    owner: int
    ships: int


def resolve_arrival_event(
    owner: int,
    garrison: float,
    arrivals: Iterable[ArrivalEvent],
) -> tuple[int, float]:
    """Resolve same-turn combat. Returns (new_owner, new_garrison).

    Faithful port of E6 cell 8 ``resolve_arrival_event`` per E1 §Combat:
        1. Group arrivals by owner; sum ships.
        2. Largest-vs-second-largest cancel; difference survives.
        3. Survivor: same owner as planet → garrison += survivor; else fight garrison
           and possibly flip ownership.
        4. Top-two tie → all attackers annihilated; garrison untouched.
    """
    arrivals = list(arrivals)
    if not arrivals:
        return owner, max(0.0, garrison)

    by_owner: dict[int, int] = {}
    for ev in arrivals:
        by_owner[ev.owner] = by_owner.get(ev.owner, 0) + int(ev.ships)
    if not by_owner:
        return owner, max(0.0, garrison)

    sorted_attackers = sorted(by_owner.items(), key=lambda kv: kv[1], reverse=True)
    top_owner, top_ships = sorted_attackers[0]

    if len(sorted_attackers) > 1:
        second_ships = sorted_attackers[1][1]
        if top_ships == second_ships:
            survivor_owner, survivor_ships = -1, 0  # mutual annihilation
        else:
            survivor_owner, survivor_ships = top_owner, top_ships - second_ships
    else:
        survivor_owner, survivor_ships = top_owner, top_ships

    if survivor_ships <= 0:
        return owner, max(0.0, garrison)
    if owner == survivor_owner:
        return owner, garrison + survivor_ships

    garrison_remaining = garrison - survivor_ships
    if garrison_remaining < 0:
        return survivor_owner, -garrison_remaining
    return owner, garrison_remaining


@dataclass(frozen=True, slots=True)
class PlanetTimeline:
    """Per-turn ownership/garrison projection over a horizon."""

    planet_id: int
    horizon: int
    owner_at: tuple[int, ...]  # length horizon+1; index 0 is "now"
    ships_at: tuple[float, ...]

    def at(self, turn: int) -> tuple[int, float]:
        idx = max(0, min(turn, self.horizon))
        return self.owner_at[idx], self.ships_at[idx]


def _simulate_timeline(
    initial_owner: int,
    initial_ships: float,
    initial_production: int,
    is_comet: bool,
    arrivals: Iterable[ArrivalEvent],
    horizon: int,
) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """Walk turn-by-turn from now to ``horizon``; output (owner_at, ships_at) per turn.

    Comets do NOT produce until owned (production = 1 if owned). Planets produce
    their listed value when owned. Combat resolves AFTER production each turn.
    """
    owner_at: list[int] = [initial_owner]
    ships_at: list[float] = [float(max(0.0, initial_ships))]

    arrivals_by_turn: dict[int, list[ArrivalEvent]] = {}
    for ev in arrivals:
        if 1 <= ev.eta <= horizon:
            arrivals_by_turn.setdefault(ev.eta, []).append(ev)

    cur_owner = initial_owner
    cur_ships = float(max(0.0, initial_ships))
    production = 1 if is_comet else int(initial_production)

    for turn in range(1, horizon + 1):
        # Phase 4: production (only if owned by a real player; neutral = -1 doesn't produce)
        if cur_owner != -1:
            cur_ships += production
        # Phase 7: combat resolution from this turn's arrivals
        cur_owner, cur_ships = resolve_arrival_event(
            cur_owner, cur_ships, arrivals_by_turn.get(turn, [])
        )
        owner_at.append(cur_owner)
        ships_at.append(max(0.0, cur_ships))

    return tuple(owner_at), tuple(ships_at)


# ---------------------------------------------------------------------------
# Fleet ETA & moving-target intercept
# ---------------------------------------------------------------------------


def estimate_fleet_eta(
    src: Planet,
    target_xy: tuple[float, float],
    target_radius: float,
    ships: int,
    *,
    sun_center: tuple[float, float] = SUN_CENTER,
    sun_radius: float = SUN_RADIUS,
    safety: float = SUN_SAFETY,
) -> tuple[float, int] | None:
    """Estimate (angle, eta_turns) for a fleet of ``ships`` from ``src`` to ``target_xy``.

    Returns ``None`` if the straight-line path is sun-blocked. ETA rounded UP to the
    next integer turn (since combat resolves at turn boundaries).
    """
    res = safe_angle_and_distance(
        src.x, src.y, src.radius,
        target_xy[0], target_xy[1], target_radius,
        sun_center=sun_center, sun_radius=sun_radius, safety=safety,
    )
    if res is None:
        return None
    angle, hit_distance = res
    speed = fleet_speed(ships)
    eta = max(1, int(math.ceil(hit_distance / max(speed, 1e-6))))
    return angle, eta


def predict_target_position(
    target: Planet,
    initial: Planet | None,  # kept for API compat; unused now (see note)
    angular_velocity: float,
    turns_ahead: int,
    *,
    comet_path: list[tuple[float, float]] | None = None,
    comet_path_index: int = 0,
) -> tuple[float, float]:
    """Forecast target position ``turns_ahead`` from now.

    Important: rotate from the target's CURRENT position, NOT from
    ``initial_planets``. At step N obs, the planet has undergone (N-1) rotations
    from initial — so rotating from initial by ``turns_ahead`` gives the wrong
    answer (off by ~angular_velocity*radius units, constant per game).
    Rotating from current by ``turns_ahead`` gives the right answer regardless
    of step number (which the agent doesn't know).

    Comets have explicit ``paths`` from the env; if ``comet_path`` is supplied,
    look it up directly.

    The ``initial`` parameter is retained for API compatibility but unused.
    """
    if comet_path is not None:
        idx = min(comet_path_index + max(0, turns_ahead), len(comet_path) - 1)
        return comet_path[idx]
    if angular_velocity != 0.0:
        return predict_planet_position(target, angular_velocity, turns_ahead)
    return target.x, target.y


def path_collision_predicted(
    src: Planet,
    target: Planet,
    angle: float,
    ships: int,
    eta: int,
    *,
    view: ObservationView,
    comet_paths: dict[int, list[tuple[float, float]]] | None = None,
    comet_path_indices: dict[int, int] | None = None,
    skip_own: bool = True,
) -> Planet | None:
    """Walk the planned fleet trajectory turn-by-turn using continuous swept-pair
    collision detection. Return the first planet (other than src and target) that
    would intercept the fleet, or None if the path is clear.

    Per env master (commit 6458c31): the env now uses `swept_pair_hit` to check
    if a fleet's per-tick segment and a planet's per-tick segment come within
    `planet.radius` of each other at any time t in [0, 1]. This catches both:
      - Fleet trajectory crossing a planet's path (old "fleet → static planet" check)
      - Planet rotating into a fleet's position (old "moving planet sweeps fleet")
    AND correctly REJECTS false positives where a planet rotates AWAY from the
    fleet during the same tick (the old point-distance check would falsely flag
    those as collisions).

    If ``skip_own`` is True, ignore collisions with the player's own planets — the
    fleet ships are added to that planet's garrison (no loss), which is acceptable.
    Set False to be conservative.

    We use `planet.radius + LAUNCH_CLEARANCE` as the collision threshold (a 0.1
    safety margin over env's strict `planet.radius`) — being slightly conservative
    at the agent's planning layer is preferable to losing fleets the env destroys.

    Position prediction per turn t:
    - Fleet: linear from old=(sx + dx*speed*(t-1), sy + dy*speed*(t-1)) to
      new=(sx + dx*speed*t, sy + dy*speed*t)
    - Orbiting planet: rotate from CURRENT position by (t-1) and t rotations (NOT
      from initial_planets — off-by-N bug otherwise)
    - Comet: index into comet_paths[planet_id] at idx_now+(t-1) and idx_now+t,
      capped at len(path)-1 (linear trajectories along discrete waypoints)
    """
    speed = fleet_speed(ships)
    sx = src.x + math.cos(angle) * (src.radius + LAUNCH_CLEARANCE)
    sy = src.y + math.sin(angle) * (src.radius + LAUNCH_CLEARANCE)
    dx = math.cos(angle)
    dy = math.sin(angle)

    for t in range(1, eta + 1):
        # Fleet positions at the START and END of turn t (one tick of motion).
        fleet_old = (sx + dx * speed * (t - 1), sy + dy * speed * (t - 1))
        fleet_new = (sx + dx * speed * t, sy + dy * speed * t)

        for p in view.planets:
            if p.id == src.id or p.id == target.id:
                continue
            if skip_own and p.owner == view.player:
                continue
            # Predict p's start-of-turn and end-of-turn positions for this tick.
            if comet_paths is not None and p.id in comet_paths:
                path = comet_paths[p.id]
                idx_now = (comet_path_indices or {}).get(p.id, 0)
                idx_old = min(idx_now + (t - 1), len(path) - 1)
                idx_new = min(idx_now + t, len(path) - 1)
                planet_old = path[idx_old]
                planet_new = path[idx_new]
            else:
                planet_old = predict_planet_position(p, view.angular_velocity, t - 1)
                planet_new = predict_planet_position(p, view.angular_velocity, t)
            if swept_pair_hit(fleet_old, fleet_new, planet_old, planet_new,
                              p.radius + LAUNCH_CLEARANCE):
                return p
    return None


def aim_with_prediction(
    src: Planet,
    target: Planet,
    ships: int,
    *,
    initial: Planet | None,
    angular_velocity: float,
    comet_path: list[tuple[float, float]] | None = None,
    comet_path_index: int = 0,
    max_iters: int = 5,
    tolerance: float = 1.0,
) -> tuple[float, int, tuple[float, float]] | None:
    """5-iteration intercept solver for moving targets (E6 cell 7).

    Returns ``(angle, eta, predicted_target_xy)`` or ``None`` if no sun-safe shot exists.
    For static targets the loop converges in one iteration.

    For comets, the projected fleet ETA is capped at the comet's remaining lifetime.
    If the fleet would arrive AFTER the comet leaves the board, returns ``None`` —
    every such launch is wasted (E6 ``COMET_MAX_CHASE_TURNS`` pattern).
    """
    is_moving = (initial is not None and angular_velocity != 0.0) or comet_path is not None

    # Comet lifetime cap: how many more turns will the comet exist?
    if comet_path is not None:
        remaining_life = max(0, len(comet_path) - comet_path_index - 1)
    else:
        remaining_life = None

    est = estimate_fleet_eta(src, (target.x, target.y), target.radius, ships)
    if est is None:
        return None
    angle, eta = est
    target_xy = (target.x, target.y)

    if remaining_life is not None and eta > remaining_life:
        return None  # comet will have left the board before fleet arrives

    if not is_moving:
        return angle, eta, target_xy

    for _ in range(max_iters):
        new_xy = predict_target_position(
            target, initial, angular_velocity, eta,
            comet_path=comet_path, comet_path_index=comet_path_index,
        )
        new_est = estimate_fleet_eta(src, new_xy, target.radius, ships)
        if new_est is None:
            return None
        new_angle, new_eta = new_est
        if remaining_life is not None and new_eta > remaining_life:
            return None
        if (
            abs(new_xy[0] - target_xy[0]) < 0.3
            and abs(new_xy[1] - target_xy[1]) < 0.3
            and abs(new_eta - eta) <= tolerance
        ):
            return new_angle, new_eta, new_xy
        angle, eta, target_xy = new_angle, new_eta, new_xy

    return angle, eta, target_xy


# ---------------------------------------------------------------------------
# WorldModel
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WorldModel:
    """Per-turn snapshot of the world with cached forecasts.

    Build with :meth:`from_observation`. Once built, query
    :meth:`projected_state`, :meth:`min_ships_to_own_by`, and
    :meth:`reinforcement_needed_to_hold_until` cheaply (most call sites are
    O(horizon) bounded by the timeline length).
    """

    obs: ObservationView
    horizon: int
    arrivals_by_planet: dict[int, list[ArrivalEvent]]
    base_timeline: dict[int, PlanetTimeline]
    comet_paths: dict[int, list[tuple[float, float]]] = field(default_factory=dict)
    comet_path_indices: dict[int, int] = field(default_factory=dict)

    @classmethod
    def from_observation(
        cls,
        obs: ObservationView,
        *,
        horizon: int = DEFAULT_HORIZON,
    ) -> WorldModel:
        arrivals_by_planet = _build_arrival_ledger(obs)
        comet_paths, comet_indices = _build_comet_paths(obs)

        timelines: dict[int, PlanetTimeline] = {}
        for planet in obs.planets:
            owner_at, ships_at = _simulate_timeline(
                initial_owner=planet.owner,
                initial_ships=planet.ships,
                initial_production=planet.production,
                is_comet=obs.is_comet(planet.id),
                arrivals=arrivals_by_planet.get(planet.id, []),
                horizon=horizon,
            )
            timelines[planet.id] = PlanetTimeline(
                planet_id=planet.id,
                horizon=horizon,
                owner_at=owner_at,
                ships_at=ships_at,
            )

        return cls(
            obs=obs,
            horizon=horizon,
            arrivals_by_planet=arrivals_by_planet,
            base_timeline=timelines,
            comet_paths=comet_paths,
            comet_path_indices=comet_indices,
        )

    def projected_state(
        self,
        target_id: int,
        eval_turn: int,
        *,
        extra_arrivals: tuple[ArrivalEvent, ...] = (),
    ) -> tuple[int, float]:
        """Return (owner, ships) at ``eval_turn`` for ``target_id``, optionally adding extra arrivals."""
        planet = self.obs.planet_by_id(target_id)
        if planet is None:
            return -1, 0.0
        if not extra_arrivals:
            return self.base_timeline[target_id].at(eval_turn)
        owner_at, ships_at = _simulate_timeline(
            initial_owner=planet.owner,
            initial_ships=planet.ships,
            initial_production=planet.production,
            is_comet=self.obs.is_comet(target_id),
            arrivals=list(self.arrivals_by_planet.get(target_id, [])) + list(extra_arrivals),
            horizon=self.horizon,
        )
        idx = max(0, min(eval_turn, self.horizon))
        return owner_at[idx], ships_at[idx]

    def min_ships_to_own_by(
        self,
        target_id: int,
        eval_turn: int,
        attacker_owner: int,
        *,
        arrival_turn: int | None = None,
        extra_arrivals: tuple[ArrivalEvent, ...] = (),
        upper_bound: int | None = None,
    ) -> int | None:
        """Minimum ships to own ``target_id`` at ``eval_turn`` from ``attacker_owner``.

        Exponential search up to a cap, then binary search. Returns ``None`` if
        even the cap doesn't suffice.
        """
        if arrival_turn is None:
            arrival_turn = eval_turn
        owner_now, ships_now = self.projected_state(target_id, eval_turn, extra_arrivals=extra_arrivals)
        if owner_now == attacker_owner:
            return 0

        def owns_at(ships: int) -> bool:
            attempt = extra_arrivals + (ArrivalEvent(eta=arrival_turn, owner=attacker_owner, ships=ships),)
            owner, _ = self.projected_state(target_id, eval_turn, extra_arrivals=attempt)
            return owner == attacker_owner

        cap = upper_bound or max(8, int(math.ceil(ships_now)) + 16)
        # Exponential growth until cap satisfies
        hi = max(1, cap)
        # Cap absolute size to a safe ceiling for blowup protection.
        hard_ceiling = 5000
        while hi <= hard_ceiling and not owns_at(hi):
            hi *= 2
        if hi > hard_ceiling and not owns_at(hard_ceiling):
            return None

        lo = 1
        while lo < hi:
            mid = (lo + hi) // 2
            if owns_at(mid):
                hi = mid
            else:
                lo = mid + 1
        return lo

    def reinforcement_needed_to_hold_until(
        self,
        target_id: int,
        hold_until: int,
        *,
        arrival_turn: int = 1,
        defender: int | None = None,
        extra_arrivals: tuple[ArrivalEvent, ...] = (),
    ) -> int | None:
        """Minimum reinforcement (defender ships) arriving at ``arrival_turn`` to hold through ``hold_until``.

        Adopts E9's full-window survival check (per synthesis §5.B):
        reinforcement is sufficient iff the defender owns the planet at every
        turn from ``arrival_turn`` to ``hold_until``.
        """
        defender = defender if defender is not None else self.obs.player

        def holds(ships: int) -> bool:
            attempt = extra_arrivals + (ArrivalEvent(eta=arrival_turn, owner=defender, ships=ships),)
            for t in range(arrival_turn, min(hold_until, self.horizon) + 1):
                owner, _ = self.projected_state(target_id, t, extra_arrivals=attempt)
                if owner != defender:
                    return False
            return True

        if holds(0):
            return 0
        hi = 8
        hard_ceiling = 5000
        while hi <= hard_ceiling and not holds(hi):
            hi *= 2
        if hi > hard_ceiling and not holds(hard_ceiling):
            return None
        lo = 1
        while lo < hi:
            mid = (lo + hi) // 2
            if holds(mid):
                hi = mid
            else:
                lo = mid + 1
        return lo


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_arrival_ledger(obs: ObservationView) -> dict[int, list[ArrivalEvent]]:
    """Project all in-flight enemy/friendly fleets forward to their target planets.

    For each fleet, find which planet (if any) it intercepts on its current
    heading. Use a coarse linear projection along (cos(angle), sin(angle))
    matching the env's straight-line travel — moving planets that sweep into
    the fleet (phase 6) are NOT modeled here for simplicity; the timeline
    captures direct-hit arrivals. This is conservative for the heuristic.
    """
    ledger: dict[int, list[ArrivalEvent]] = {p.id: [] for p in obs.planets}
    static_planet_ids = {p.id: (p.x, p.y, p.radius) for p in obs.planets}

    for fleet in obs.fleets:
        speed = fleet_speed(fleet.ships)
        if speed <= 0:
            continue
        # Fleet straight-line direction
        dx = math.cos(fleet.angle)
        dy = math.sin(fleet.angle)
        # Find the nearest planet the fleet's ray will hit (within reasonable horizon).
        best: tuple[int, int] | None = None  # (planet_id, eta_turns)
        for pid, (px, py, pr) in static_planet_ids.items():
            if pid == fleet.from_planet_id:
                continue  # can't re-arrive at source on launch turn
            # Solve: minimize point-to-segment distance for the ray
            # Project (px, py) onto the ray (fleet origin + t * (dx, dy))
            ox, oy = fleet.x, fleet.y
            t = (px - ox) * dx + (py - oy) * dy
            if t <= 0:
                continue  # behind the fleet
            # Closest distance along the ray
            cx, cy = ox + t * dx, oy + t * dy
            if dist(cx, cy, px, py) <= pr + LAUNCH_CLEARANCE:
                eta = max(1, int(math.ceil(t / speed)))
                if best is None or eta < best[1]:
                    best = (pid, eta)
        if best is not None:
            pid, eta = best
            ledger[pid].append(ArrivalEvent(eta=eta, owner=fleet.owner, ships=int(fleet.ships)))

    return ledger


def _build_comet_paths(obs: ObservationView) -> tuple[dict[int, list[tuple[float, float]]], dict[int, int]]:
    paths: dict[int, list[tuple[float, float]]] = {}
    indices: dict[int, int] = {}
    for group in obs.comets:
        planet_ids = group.get("planet_ids", []) or []
        group_paths = group.get("paths", []) or []
        path_index = int(group.get("path_index", 0) or 0)
        for pid, path in zip(planet_ids, group_paths, strict=False):
            paths[int(pid)] = [tuple(map(float, pt)) for pt in path]
            indices[int(pid)] = path_index
    return paths, indices
