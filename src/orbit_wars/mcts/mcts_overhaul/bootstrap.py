"""Bootstrapper for Neural Network training data via Modal.

Runs thousands of games of heuristic vs heuristic self-play on Modal GPUs/CPUs.
Extracts the state, the chosen actions (as multi-hot token targets), and the 
final game outcome.
"""

from __future__ import annotations

import sys
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

import time
import uuid
import json
from pathlib import Path

import numpy as np

# Modal imports
import modal

# Local imports
from orbit_wars.state import ObservationView
from orbit_wars.heuristic.heuristic_overhaul.strategy import _decide_with_decisions
from orbit_wars.heuristic.heuristic_overhaul.config import HeuristicConfig
from orbit_wars.mcts.token import LaunchToken
from orbit_wars.mcts.mcts_overhaul.features import extract_features, STATE_DIM
from orbit_wars.mcts.mcts_overhaul.dense_token import encode_dense_token, NUM_TOKENS
from orbit_wars.mcts.mcts_overhaul.config import MCTSOverhaulConfig

# Modal Setup
volume = modal.Volume.from_name("orbit-wars-vol", create_if_missing=True)

tuner_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install("numpy>=2.0", "kaggle_environments>=1.18.0")
    .add_local_dir(
        local_path=str(Path(__file__).parent.parent.parent.parent), # src/
        remote_path="/app/src",
        copy=True,
    )
)

app = modal.App("orbit-wars-nn-bootstrapper", image=tuner_image)


def get_closest_bucket(fraction: float, buckets: tuple[float, ...]) -> int:
    """Find the index of the closest bucket via pure python loops."""
    return min(range(len(buckets)), key=lambda i: abs(buckets[i] - fraction))


@app.function(
    image=tuner_image, 
    cpu=1.0, 
    memory=32768,
    timeout=3600,
    retries=modal.Retries(max_retries=5, backoff_coefficient=1.0)
)
def generate_game_data(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Plays a single game of heuristic self-play and extracts training data."""
    from kaggle_environments import make
    
    cfg = HeuristicConfig.default()
    mcts_cfg = MCTSOverhaulConfig()
    buckets = mcts_cfg.ship_fraction_buckets
    
    states_list = []
    policies_list = []
    
    # We will track data for player 0. Player 1 is just the opponent.
    def agent_p0(obs):
        view = ObservationView.from_raw(obs)
        if not view.my_planets:
            return []
            
        moves, decisions = _decide_with_decisions(obs, cfg)
        
        # Extract features
        state_vec = extract_features(view)
        
        # Multi-hot action targets
        policy_vec = np.zeros(NUM_TOKENS, dtype=np.float32)
        policy_vec[0] = 1.0 # COMMIT is always chosen eventually
        
        for dec in decisions:
            fraction = dec.ships / max(1.0, float(dec.src_ships_pre_launch))
            b_idx = get_closest_bucket(fraction, buckets)
            tok = LaunchToken(dec.src_id, dec.target_id, b_idx)
            idx = encode_dense_token(tok)
            policy_vec[idx] = 1.0
            
        states_list.append(state_vec)
        policies_list.append(policy_vec)
        
        return moves

    def agent_p1(obs):
        moves, _ = _decide_with_decisions(obs, cfg)
        return moves

    # Run game
    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run([agent_p0, agent_p1])
    
    # Determine outcome for player 0
    last_step = env.steps[-1]
    r0 = float(last_step[0].reward)
    r1 = float(last_step[1].reward)
    
    if r0 > r1:
        value = 1.0
    elif r0 < r1:
        value = -1.0
    else:
        value = 0.0
        
    N = len(states_list)
    states = np.array(states_list, dtype=np.float32)
    policies = np.array(policies_list, dtype=np.float32)
    values = np.full((N, 1), value, dtype=np.float32)
    
    return states, policies, values


@app.function(
    image=tuner_image,
	cpu=2.0,
    timeout=86400, 
    memory=340992,
    volumes={"/data": volume}
)
def remote_main(num_games: int = 100):
    """Heavy orchestrator running entirely in the cloud."""
    print(f"Starting bootstrap generation for {num_games} games...")
    out_path = Path("/data/nn_bootstrap")
    out_path.mkdir(parents=True, exist_ok=True)
    
    all_states = []
    all_policies = []
    all_values = []
    
    start_time = time.time()
    
    # Generate random seeds
    seeds = [int(uuid.uuid4().int % 1000000) for _ in range(num_games)]
    
    # Dispatch in parallel
    for states, policies, values in generate_game_data.map(seeds):
        all_states.append(states)
        all_policies.append(policies)
        all_values.append(values)
        
    print(f"Finished simulating {num_games} games in {time.time() - start_time:.2f}s")
    
    # Concatenate dataset
    S = np.concatenate(all_states, axis=0)
    P = np.concatenate(all_policies, axis=0)
    V = np.concatenate(all_values, axis=0)
    
    print(f"Total dataset shape:")
    print(f"  States: {S.shape}")
    print(f"  Policies: {P.shape}")
    print(f"  Values: {V.shape}")
    
    # Save to the persistent volume
    run_id = int(time.time())
    file_path = out_path / f"dataset_{run_id}.npz"
    np.savez_compressed(file_path, states=S, policies=P, values=V)
    print(f"Saved dataset to volume at {file_path}")
    
    # Explicitly commit the volume
    volume.commit()


@app.local_entrypoint()
def main(num_games: int = 100):
    """Entrypoint to run mass dataset generation on Modal."""
    remote_main.remote(num_games)
