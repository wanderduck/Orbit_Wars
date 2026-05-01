"""Competent sniper opponent.

Stronger than ``starter`` (which only targets static planets and aims at
current position): targets ANY non-owned planet, predicts orbital position
at arrival via fixed-point iteration, sends ``target.ships + 1``, no defense
or path-clearance. Mid-tier sparring partner.

Deliberate weaknesses (so we can find scenarios v1.5 still loses):
- No defense — won't reinforce threatened planets.
- No path-clearance — fleets can be intercepted by other planets en route.
- No ship-budget tracking — happily sends ships from a planet about to fall.
- Sniper rule (target.ships+1) ignores production during transit.
"""

from __future__ import annotations

import math
from typing import Any

# Mirror the env's constants without importing the env (keeps this file
# loadable as a Kaggle agent if ever needed standalone).
_BOARD_CENTER: float = 50.0
_SHIP_SPEED_MAX: float = 6.0


def _obs_get(obs: Any, key: str, default: Any = None) -> Any:
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


def _fleet_speed(ships: int) -> float:
    """Match env.fleet_speed: speed scales sublinearly with fleet size."""
    if ships <= 0:
        return 1.0
    speed = 1.0 + (_SHIP_SPEED_MAX - 1.0) * (math.log(ships) / math.log(1000.0)) ** 1.5
    return min(max(speed, 1.0), _SHIP_SPEED_MAX)


def _predict_orbital(target_x: float, target_y: float, ang_vel: float, eta: int) -> tuple[float, float]:
    """Where will an orbiting planet be after ``eta`` turns?"""
    rx = target_x - _BOARD_CENTER
    ry = target_y - _BOARD_CENTER
    radius = math.hypot(rx, ry)
    if radius < 1e-6:
        return target_x, target_y
    theta = math.atan2(ry, rx) + ang_vel * eta
    return _BOARD_CENTER + radius * math.cos(theta), _BOARD_CENTER + radius * math.sin(theta)


def agent(obs: Any) -> list[list[float | int]]:
    raw_planets = _obs_get(obs, "planets", []) or []
    planets = [tuple(p) for p in raw_planets]  # (id, owner, x, y, radius, ships, production)
    if not planets:
        return []

    player = int(_obs_get(obs, "player", 0) or 0)
    ang_vel = float(_obs_get(obs, "angular_velocity", 0.0) or 0.0)

    my_planets = [p for p in planets if p[1] == player]
    targets = [p for p in planets if p[1] != player]
    if not my_planets or not targets:
        return []

    moves: list[list[float | int]] = []
    for src in my_planets:
        src_id, _owner, sx, sy, _sr, src_ships, _prod = src
        if src_ships < 20:
            continue

        # Pick nearest target (current position).
        best_target = None
        best_dist = math.inf
        for t in targets:
            _tid, _to, tx, ty, _tr, _ts, _tp = t
            d = math.hypot(tx - sx, ty - sy)
            if d < best_dist:
                best_dist = d
                best_target = t
        if best_target is None:
            continue

        tid, _to, tx, ty, tr, ts, _tp = best_target
        ships_send = max(int(ts) + 1, 20)
        if ships_send > src_ships:
            continue

        # Fixed-point intercept solve (3 iterations is plenty at our distances).
        speed = _fleet_speed(ships_send)
        pred_x, pred_y = tx, ty
        for _ in range(3):
            d = max(math.hypot(pred_x - sx, pred_y - sy) - tr, 0.0)
            eta = max(1, int(math.ceil(d / speed)))
            pred_x, pred_y = _predict_orbital(tx, ty, ang_vel, eta)

        angle = math.atan2(pred_y - sy, pred_x - sx)
        moves.append([int(src_id), float(angle), int(ships_send)])

    return moves
