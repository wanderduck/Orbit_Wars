"""Defensive turtle opponent.

Hold ships unless an opportunity is cheap. Reinforce own planets that have
incoming enemy fleets. The turtle should stockpile relative to opponents
who launch into bad positions, then opportunistically strike when targets
are weakened.

Heuristics:
- Attack only targets with ``ships < 30`` and only if the source can spare
  at least ``ships + 5``.
- Reinforce: any owned planet whose incoming enemy ship count exceeds its
  own garrison gets the nearest viable source's reinforcement up to half
  the source's ships.
- Aim at current position (target movement is unaccounted for).
"""

from __future__ import annotations

import math
from typing import Any

_RAID_SHIPS_MAX: int = 30
_RAID_RESERVE: int = 5  # extra ships above target.ships to ensure capture
_MIN_SPARE_AFTER_RAID: int = 15


def _obs_get(obs: Any, key: str, default: Any = None) -> Any:
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


def _threat_by_planet(
    fleets: list[tuple], my_planets: list[tuple], player: int,
) -> dict[int, int]:
    """Assign each enemy fleet to its nearest owned planet within 25 units."""
    out: dict[int, int] = {}
    for f in fleets:
        _fid, f_owner, fx, fy, _ang, _src, f_ships = f
        if f_owner == player:
            continue
        nearest = min(
            ((mp, math.hypot(mp[2] - fx, mp[3] - fy)) for mp in my_planets),
            key=lambda x: x[1],
            default=None,
        )
        if nearest is not None and nearest[1] < 25.0:
            out[nearest[0][0]] = out.get(nearest[0][0], 0) + int(f_ships)
    return out


def _plan_reinforcements(
    my_planets: list[tuple], threats: dict[int, int], used: dict[int, int],
) -> list[list[float | int]]:
    moves: list[list[float | int]] = []
    for tgt in my_planets:
        tgt_id, _o, tx, ty, _tr, tgt_ships, _tp = tgt
        deficit = threats.get(tgt_id, 0) - int(tgt_ships)
        if deficit <= 0:
            continue
        sources = sorted(
            (p for p in my_planets if p[0] != tgt_id),
            key=lambda p: math.hypot(p[2] - tx, p[3] - ty),
        )
        for src in sources:
            src_id, _so, sx, sy, _sr, src_ships, _sp = src
            available = int(src_ships) - used.get(src_id, 0)
            send = min(available // 2, deficit + _RAID_RESERVE)
            if send < 20:
                continue
            angle = math.atan2(ty - sy, tx - sx)
            moves.append([int(src_id), float(angle), int(send)])
            used[src_id] = used.get(src_id, 0) + send
            break
    return moves


def _plan_raids(
    my_planets: list[tuple], targets: list[tuple], used: dict[int, int],
) -> list[list[float | int]]:
    moves: list[list[float | int]] = []
    for src in my_planets:
        src_id, _so, sx, sy, _sr, src_ships, _sp = src
        available = int(src_ships) - used.get(src_id, 0)
        if available < 20 + _MIN_SPARE_AFTER_RAID:
            continue
        best = None
        best_dist = math.inf
        for t in targets:
            _tid, _to, tx, ty, _tr, t_ships, _tp = t
            cost = int(t_ships) + _RAID_RESERVE
            if cost + _MIN_SPARE_AFTER_RAID > available:
                continue
            d = math.hypot(tx - sx, ty - sy)
            if d < best_dist:
                best_dist = d
                best = t
        if best is None:
            continue
        _tid, _to, tx, ty, _tr, t_ships, _tp = best
        send = int(t_ships) + _RAID_RESERVE
        angle = math.atan2(ty - sy, tx - sx)
        moves.append([int(src_id), float(angle), int(send)])
        used[src_id] = used.get(src_id, 0) + send
    return moves


def agent(obs: Any) -> list[list[float | int]]:
    raw_planets = _obs_get(obs, "planets", []) or []
    raw_fleets = _obs_get(obs, "fleets", []) or []
    planets = [tuple(p) for p in raw_planets]  # (id, owner, x, y, radius, ships, production)
    fleets = [tuple(f) for f in raw_fleets]    # (id, owner, x, y, angle, from_planet_id, ships)

    if not planets:
        return []

    player = int(_obs_get(obs, "player", 0) or 0)
    my_planets = [p for p in planets if p[1] == player]
    if not my_planets:
        return []

    used: dict[int, int] = {}
    threats = _threat_by_planet(fleets, my_planets, player)
    moves = _plan_reinforcements(my_planets, threats, used)

    targets = [p for p in planets if p[1] != player and p[5] < _RAID_SHIPS_MAX]
    if targets:
        moves.extend(_plan_raids(my_planets, targets, used))
    return moves
