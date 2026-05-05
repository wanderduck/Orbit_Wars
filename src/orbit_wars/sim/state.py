"""Mutable state representation for the MCTS forward-model simulator.

Mirrors the kaggle_environments orbit_wars env's INTERNAL state (not the
per-player observation). Every field needed to step the world by one turn
lives here. See `docs/research_documents/mcts_forward_model_design.md`
Section 3.1 for the full schema spec.

This is the data structure that flows through `Simulator.step()` and is
compared by `ForwardModelValidator`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "SimConfig",
    "SimCometGroup",
    "SimFleet",
    "SimPlanet",
    "SimState",
]


@dataclass(slots=True)
class SimConfig:
    """Per-episode constants. Defaults match env spec
    `.venv/.../kaggle_environments/envs/orbit_wars/orbit_wars.json`.
    """

    episode_steps: int = 500
    act_timeout: float = 1.0
    ship_speed: float = 6.0          # MAX_SPEED in env L521
    comet_speed: float = 4.0         # configuration.cometSpeed in env L443
    num_agents: int = 2              # 2 or 4


@dataclass(slots=True)
class SimPlanet:
    """One planet (or comet — comets are aliased into the planet list per env L48)."""

    id: int
    x: float
    y: float
    radius: float
    owner: int                       # -1 = neutral
    ships: float                     # env stores as int; we use float for sub-tick combat math
    production: int
    is_comet: bool = False           # True if this planet's id is in obs.comet_planet_ids


@dataclass(slots=True)
class SimFleet:
    """One in-flight fleet."""

    id: int                          # globally unique within episode (env's next_fleet_id)
    owner: int
    from_planet_id: int
    target_planet_id: int            # the planet the player AIMED at (used for combat routing)
    x: float
    y: float
    angle: float                     # radians
    ships: int
    spawned_at_step: int


@dataclass(slots=True)
class SimCometGroup:
    """One comet group. Per env L441-477: each spawn event creates ONE group with up to 4
    symmetric comets. Each comet inside the group has its own pre-computed path.
    """

    planet_ids: list[int]            # the SimPlanet IDs (with is_comet=True) that belong to this group
    paths: list[list[tuple[float, float]]]  # paths[i] is the trajectory for planet_ids[i]
    path_index: int                  # current index into each path (-1 = pre-spawn)


@dataclass(slots=True)
class SimState:
    """Complete mutable env state. Built from an extracted env snapshot;
    mutated in place by `Simulator.step()` (which deepcopies before mutation).
    """

    step: int                        # current turn (env uses 0-indexed; we follow)
    planets: list[SimPlanet]         # all planets, including comet-aliased
    fleets: list[SimFleet]           # all in-flight fleets
    comet_groups: list[SimCometGroup]
    angular_velocity: float          # global, fixed per game (sampled at episode init)
    next_fleet_id: int               # env's monotonic fleet ID counter
    config: SimConfig

    # Frozen snapshot of planets at game start, used for rotation reference.
    # Per env L572-590: rotation angle is computed from initial position, not
    # current. Required to match the env's deterministic rotation math.
    initial_planets: list[SimPlanet] = field(default_factory=list)

    def planet_by_id(self, pid: int) -> SimPlanet | None:
        for p in self.planets:
            if p.id == pid:
                return p
        return None

    def player_planets(self, player_id: int) -> list[SimPlanet]:
        return [p for p in self.planets if p.owner == player_id]

    def alive_players(self) -> set[int]:
        """Per env L687-693: a player is alive if they own >=1 planet OR have >=1 fleet in flight."""
        alive: set[int] = set()
        for p in self.planets:
            if p.owner != -1:
                alive.add(p.owner)
        for f in self.fleets:
            alive.add(f.owner)
        return alive
