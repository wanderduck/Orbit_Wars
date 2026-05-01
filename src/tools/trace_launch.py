"""Manually trace specific launches to verify the path-collision hypothesis.

For each launch we examine:
1. The src→target ray.
2. ALL other planets at the launch turn — for each, compute closest approach
   to the ray (along the forward direction from src). List planets within
   `(radius + LAUNCH_CLEARANCE)` of the ray, sorted by distance from src.
3. Walk env.steps forward from launch turn, finding the fleet that owner=0
   launched, and tracking it until disappearance. The disappearance turn and
   position tell us where the fleet was destroyed.

Usage::

    uv run python -m tools.trace_launch --seed 0 --n 5
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import typer
from kaggle_environments import make
from rich.console import Console
from rich.table import Table

import sys
sys.path.insert(0, "src")
import main as main_module
from orbit_wars.geometry import (
    LAUNCH_CLEARANCE,
    SUN_CENTER,
    SUN_RADIUS,
    SUN_SAFETY,
    point_to_segment_distance,
)
from orbit_wars.heuristic.config import HeuristicConfig
from orbit_wars.heuristic.strategy import decide_with_decisions

app = typer.Typer(help="Per-launch tracer for the v1.1 diagnostic verification.")
console = Console()


@dataclass
class RayCandidate:
    planet_id: int
    is_target: bool
    distance_along_ray: float
    closest_approach: float
    planet_radius: float
    will_collide: bool


def planets_on_ray(src_xy: tuple[float, float], src_radius: float,
                    angle: float, all_planets: list,
                    target_id: int) -> list[RayCandidate]:
    """For the ray from src outward at `angle`, list planets sorted by distance along ray."""
    sx, sy = src_xy
    dx, dy = math.cos(angle), math.sin(angle)
    # Start a tiny bit past the launching planet so we don't hit it
    start_x = sx + dx * (src_radius + LAUNCH_CLEARANCE)
    start_y = sy + dy * (src_radius + LAUNCH_CLEARANCE)

    candidates: list[RayCandidate] = []
    for p in all_planets:
        # Project p onto the ray
        px, py = p[2], p[3]
        radius = p[4]
        t = (px - start_x) * dx + (py - start_y) * dy
        if t <= 0:
            continue  # behind src
        # Closest approach point on the ray
        cx = start_x + t * dx
        cy = start_y + t * dy
        d = math.hypot(px - cx, py - cy)
        will_collide = d <= radius + LAUNCH_CLEARANCE
        candidates.append(RayCandidate(
            planet_id=p[0],
            is_target=(p[0] == target_id),
            distance_along_ray=t,
            closest_approach=d,
            planet_radius=radius,
            will_collide=will_collide,
        ))
    candidates.sort(key=lambda c: c.distance_along_ray)
    return candidates


def trace_fleet(env, launch_step: int, src_id: int, target_id: int,
                ships: int, angle: float) -> dict[str, Any]:
    """Walk env.steps from launch_step forward; find this launch's fleet by matching attributes."""
    info: dict[str, Any] = {"first_seen_step": None, "last_seen_step": None,
                            "trajectory": [], "disappeared_at_planet": None}
    # Find the fleet first appearing in step `launch_step + 1`
    fleet_id = None
    for step_idx in range(launch_step + 1, min(launch_step + 5, len(env.steps))):
        obs = env.steps[step_idx][0].observation
        for f in obs.fleets:
            # f = [id, owner, x, y, angle, from_planet_id, ships]
            if (f[1] == 0 and f[5] == src_id and f[6] == ships
                    and abs(f[4] - angle) < 0.01):
                fleet_id = f[0]
                info["first_seen_step"] = step_idx
                info["trajectory"].append((step_idx, f[2], f[3]))
                break
        if fleet_id is not None:
            break

    if fleet_id is None:
        info["error"] = "fleet never appeared (consumed in same turn?)"
        return info

    # Walk forward tracking this fleet
    last_pos = info["trajectory"][0]
    for step_idx in range(info["first_seen_step"] + 1, min(info["first_seen_step"] + 30, len(env.steps))):
        obs = env.steps[step_idx][0].observation
        f = next((ff for ff in obs.fleets if ff[0] == fleet_id), None)
        if f is None:
            info["last_seen_step"] = step_idx - 1
            # Where did it disappear? Check planets near last_pos
            last_x, last_y = last_pos[1], last_pos[2]
            # Walk forward from last_pos by speed in 1 turn
            # to estimate where in the next-step it would have been
            disappeared_near = None
            for p in obs.planets:
                pid, pow_, px, py, pradius, _, _ = p[0], p[1], p[2], p[3], p[4], p[5], p[6]
                d = math.hypot(px - last_x, py - last_y)
                if d <= pradius + 3.0:  # 3-unit slack for one turn of fleet movement
                    disappeared_near = {"planet_id": pid, "owner": pow_, "distance": d, "radius": pradius}
                    break
            # Sun?
            sun_d = math.hypot(last_x - SUN_CENTER[0], last_y - SUN_CENTER[1])
            info["disappeared_at_planet"] = disappeared_near
            info["disappeared_near_sun"] = sun_d <= SUN_RADIUS + SUN_SAFETY + 3.0
            info["disappeared_at_pos"] = last_pos
            return info
        last_pos = (step_idx, f[2], f[3])
        info["trajectory"].append(last_pos)

    info["last_seen_step"] = info["first_seen_step"] + 30
    info["error"] = "still in flight after 30 turns"
    return info


@app.command()
def trace(seed: int = 0, n: int = 5,
          launch_step_min: int = 5, launch_step_max: int = 200,
          target_type: str = "orbiting") -> None:
    """Trace `n` misses in seed `seed`, between turns min..max.

    target_type ∈ {'static', 'orbiting', 'comet'} — pick which kind to trace.
    """
    random.seed(42)
    env = make("orbit_wars", debug=False, configuration={"seed": seed})
    env.run([main_module.agent, "random"])

    cfg = HeuristicConfig.default()
    traced = 0
    for step_idx in range(launch_step_min, min(launch_step_max, len(env.steps))):
        if traced >= n:
            break
        obs = env.steps[step_idx][0].observation
        moves, decisions = decide_with_decisions(obs, cfg)
        if not decisions:
            continue
        for d in decisions:
            # Filter by target type
            if target_type == "static" and not d.target_is_static:
                continue
            if target_type == "orbiting" and (d.target_is_static or d.target_is_comet):
                continue
            if target_type == "comet" and not d.target_is_comet:
                continue
            # Verify this is a MISS by checking the actual outcome at arrival
            arrival_step = step_idx + d.eta + 2  # 2-turn slack
            if arrival_step >= len(env.steps):
                continue
            arr_obs = env.steps[arrival_step][0].observation
            arr_target = next((p for p in arr_obs.planets if p[0] == d.target_id), None)
            if arr_target is None:
                continue  # comet vanished
            if arr_target[1] == 0:
                continue  # captured — not a miss
            # Trace this launch
            console.print(f"\n[bold cyan]LAUNCH at step {step_idx}[/bold cyan]")
            console.print(f"  src={d.src_id} pos=({d.target_x:.1f},{d.target_y:.1f}) target={d.target_id} owner={d.target_owner} static={d.target_is_static}")
            console.print(f"  ships={d.ships} angle={d.angle:.3f} eta={d.eta}")

            # Get src pos
            src_planet = next((p for p in obs.planets if p[0] == d.src_id), None)
            if src_planet is None:
                continue
            src_xy = (src_planet[2], src_planet[3])
            src_r = src_planet[4]

            # All planets on ray
            cands = planets_on_ray(src_xy, src_r, d.angle, obs.planets, d.target_id)
            colliders = [c for c in cands if c.will_collide]

            tbl = Table(title="Planets on ray (sorted by distance along ray)")
            tbl.add_column("ID")
            tbl.add_column("dist_along")
            tbl.add_column("closest_approach")
            tbl.add_column("radius")
            tbl.add_column("WILL COLLIDE?")
            tbl.add_column("is_target")
            for c in cands[:10]:
                tbl.add_row(str(c.planet_id), f"{c.distance_along_ray:.1f}",
                            f"{c.closest_approach:.2f}", f"{c.planet_radius:.2f}",
                            "[red]YES[/red]" if c.will_collide else "no",
                            "[green]TARGET[/green]" if c.is_target else "-")
            console.print(tbl)

            console.print(f"  First collision: planet {colliders[0].planet_id if colliders else 'NONE'}"
                         + (f" (TARGET — fleet should reach!)" if colliders and colliders[0].is_target else
                            f" (NOT target — fleet hits planet {colliders[0].planet_id} first)" if colliders else ""))

            # Trace the actual fleet
            trace_info = trace_fleet(env, step_idx, d.src_id, d.target_id, d.ships, d.angle)
            console.print(f"  Fleet trace: first_seen={trace_info.get('first_seen_step')} "
                         f"last_seen={trace_info.get('last_seen_step')} "
                         f"trajectory_len={len(trace_info.get('trajectory', []))}")
            if trace_info.get("disappeared_at_planet"):
                p = trace_info["disappeared_at_planet"]
                console.print(f"  [yellow]Disappeared near planet {p['planet_id']} (owner={p['owner']}, r={p['radius']:.2f}, d={p['distance']:.2f})[/yellow]")
            if trace_info.get("disappeared_near_sun"):
                console.print(f"  [yellow]Disappeared near SUN[/yellow]")
            if trace_info.get("error"):
                console.print(f"  [red]{trace_info['error']}[/red]")

            traced += 1
            break  # one decision per step_idx


if __name__ == "__main__":
    app()
