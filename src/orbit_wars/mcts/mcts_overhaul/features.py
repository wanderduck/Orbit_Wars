"""Feature extraction for the Neural Network. Converts the Kaggle ObservationView or SimState into a flat 1D numpy array."""
from __future__ import annotations
import numpy as np
from orbit_wars.state import ObservationView
from orbit_wars.sim.state import SimState

MAX_PLANETS = 60
FEATURES_PER_PLANET = 9
GLOBAL_FEATURES = 1
STATE_DIM = (MAX_PLANETS * FEATURES_PER_PLANET) + GLOBAL_FEATURES

def extract_features(view: ObservationView) -> np.ndarray:
    vec = np.zeros(STATE_DIM, dtype=np.float32)
    player = view.player

    for idx, p in enumerate(view.planets):
        if idx >= MAX_PLANETS: break
        offset = idx * FEATURES_PER_PLANET

        is_mine = 1.0 if p.owner == player else 0.0
        is_neutral = 1.0 if p.owner == -1 else 0.0
        is_enemy = 1.0 if (not is_mine and not is_neutral) else 0.0

        vec[offset + 0] = is_mine
        vec[offset + 1] = is_enemy
        vec[offset + 2] = is_neutral
        vec[offset + 3] = p.ships * 0.001
        vec[offset + 4] = p.production * 0.2
        vec[offset + 5] = p.x * 0.01
        vec[offset + 6] = p.y * 0.01
        vec[offset + 7] = p.radius * 0.1
        vec[offset + 8] = 1.0 if view.is_comet(p.id) else 0.0

    vec[-1] = view.step * 0.002
    return vec

def extract_features_sim(state: SimState, player_id: int, accumulated_tokens: list | None = None) -> np.ndarray:
    vec = np.zeros(STATE_DIM, dtype=np.float32)
    deductions = {}

    if accumulated_tokens:
        buckets = (0.25, 0.5, 0.75, 1.0)
        for t in accumulated_tokens:
            if not t.is_commit():
                frac = buckets[t.ship_fraction_bucket] if t.ship_fraction_bucket < len(buckets) else 1.0
                deductions[t.src_planet_id] = deductions.get(t.src_planet_id, 0.0) + frac

    for idx, p in enumerate(state.planets):
        if idx >= MAX_PLANETS: break
        offset = idx * FEATURES_PER_PLANET

        is_mine = 1.0 if p.owner == player_id else 0.0
        is_neutral = 1.0 if p.owner == -1 else 0.0
        is_enemy = 1.0 if (not is_mine and not is_neutral) else 0.0

        # Deduct fractional ships internally to inform sub-turn action consequences
        ships = p.ships
        if is_mine > 0.0 and p.id in deductions:
            ships -= p.ships * deductions[p.id]
            ships = max(0.0, float(ships))

        vec[offset + 0] = is_mine
        vec[offset + 1] = is_enemy
        vec[offset + 2] = is_neutral
        vec[offset + 3] = ships * 0.001
        vec[offset + 4] = p.production * 0.2
        vec[offset + 5] = p.x * 0.01
        vec[offset + 6] = p.y * 0.01
        vec[offset + 7] = p.radius * 0.1
        vec[offset + 8] = 0.0

    vec[-1] = state.step * 0.002
    return vec