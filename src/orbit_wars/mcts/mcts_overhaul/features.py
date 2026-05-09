"""Feature extraction for the Neural Network.

Converts the Kaggle ObservationView or SimState into a flat 1D numpy array.
"""

from __future__ import annotations

import numpy as np
from orbit_wars.state import ObservationView
from orbit_wars.sim.state import SimState

MAX_PLANETS = 60
FEATURES_PER_PLANET = 9
GLOBAL_FEATURES = 1

STATE_DIM = (MAX_PLANETS * FEATURES_PER_PLANET) + GLOBAL_FEATURES

def extract_features(view: ObservationView) -> np.ndarray:
    """Flatten an ObservationView into a 1D tensor for NN inference."""
    vec = np.zeros(STATE_DIM, dtype=np.float32)
    
    # 1. Planet features
    for idx, p in enumerate(view.planets):
        if idx >= MAX_PLANETS:
            break
            
        offset = idx * FEATURES_PER_PLANET
        
        is_mine = 1.0 if p.owner == view.player else 0.0
        is_neutral = 1.0 if p.owner == -1 else 0.0
        is_enemy = 1.0 if (not is_mine and not is_neutral) else 0.0
        
        vec[offset + 0] = is_mine
        vec[offset + 1] = is_enemy
        vec[offset + 2] = is_neutral
        vec[offset + 3] = p.ships / 1000.0
        vec[offset + 4] = p.production / 5.0
        vec[offset + 5] = p.x / 100.0
        vec[offset + 6] = p.y / 100.0
        vec[offset + 7] = p.radius / 10.0
        vec[offset + 8] = 1.0 if view.is_comet(p.id) else 0.0

    # 2. Global features
    vec[-1] = view.step / 500.0
    
    return vec

def extract_features_sim(state: SimState, player_id: int) -> np.ndarray:
    """Flatten a SimState into a 1D tensor for NN inference during tree search."""
    vec = np.zeros(STATE_DIM, dtype=np.float32)
    
    for idx, p in enumerate(state.planets):
        if idx >= MAX_PLANETS:
            break
            
        offset = idx * FEATURES_PER_PLANET
        
        is_mine = 1.0 if p.owner == player_id else 0.0
        is_neutral = 1.0 if p.owner == -1 else 0.0
        is_enemy = 1.0 if (not is_mine and not is_neutral) else 0.0
        
        vec[offset + 0] = is_mine
        vec[offset + 1] = is_enemy
        vec[offset + 2] = is_neutral
        vec[offset + 3] = p.ships / 1000.0
        vec[offset + 4] = p.production / 5.0
        vec[offset + 5] = p.x / 100.0
        vec[offset + 6] = p.y / 100.0
        vec[offset + 7] = p.radius / 10.0
        # SimState planets don't easily track is_comet, default to 0 during deep search
        vec[offset + 8] = 0.0

    vec[-1] = state.step / 500.0
    return vec

