"""Aggressive swarm opponent.

Every owned planet with at least 20 ships launches half its garrison at its
nearest non-owned planet every turn. No prediction (current-position aim),
no defense, no path-clearance.

Tests whether v1.5 can withstand sustained volume: many small fleets coming
from multiple sources at multiple targets. The swarm wastes a lot of ships
to the sun and to interception, but the question is whether v1.5 has slack
after defending or whether continual reinforcement starves its offense.
"""

from __future__ import annotations

import math
from typing import Any


def _obs_get(obs: Any, key: str, default: Any = None) -> Any:
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


def agent(obs: Any) -> list[list[float | int]]:
    raw_planets = _obs_get(obs, "planets", []) or []
    planets = [tuple(p) for p in raw_planets]  # (id, owner, x, y, radius, ships, production)
    if not planets:
        return []

    player = int(_obs_get(obs, "player", 0) or 0)
    targets = [p for p in planets if p[1] != player]
    if not targets:
        return []

    moves: list[list[float | int]] = []
    for src in planets:
        if src[1] != player:
            continue
        src_id, _o, sx, sy, _sr, src_ships, _p = src
        ships_send = src_ships // 2
        if ships_send < 20:
            continue

        # Nearest target by current position.
        best = None
        best_dist = math.inf
        for t in targets:
            d = math.hypot(t[2] - sx, t[3] - sy)
            if d < best_dist:
                best_dist = d
                best = t
        if best is None:
            continue

        angle = math.atan2(best[3] - sy, best[2] - sx)
        moves.append([int(src_id), float(angle), int(ships_send)])

    return moves
