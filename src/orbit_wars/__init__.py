"""Orbit Wars agent package — domain model, geometry, world simulation, and heuristic strategy.

Layout:
- :mod:`orbit_wars.state`     — typed observation/planet/fleet wrappers, dual-mode ``obs`` access.
- :mod:`orbit_wars.geometry`  — distance, angles, sun-segment intersection, fleet speed, intercept.
- :mod:`orbit_wars.rotation`  — predict orbiting-planet positions at future steps.
- :mod:`orbit_wars.world`     — :class:`WorldModel`, timeline simulation, arrival-time forecasts.
- :mod:`orbit_wars.heuristic` — v1 shipping strategy (target scoring, fleet sizing, threats, comets).
- :mod:`orbit_wars.rl`        — PPO + self-play scaffold (built in v1, ships in v2+).
"""

__version__ = "0.1.0"
