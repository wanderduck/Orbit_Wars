"""Bootstrapper for Neural Network training data via Local Multiprocessing.
Runs thousands of games of heuristic vs heuristic self-play on local CPU cores.
Extracts the state, chosen actions (as multi-hot targets), and final game outcome,
saving them in memory-safe rolling chunks to prevent RAM exhaustion.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
import argparse
import concurrent.futures
from pathlib import Path
import numpy as np

# Dynamically add the 'src' root to sys.path so 'orbit_wars' modules can be imported naturally
project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
	sys.path.insert(0, project_root)

# Local imports
from orbit_wars.state import ObservationView
from orbit_wars.heuristic.heuristic_overhaul.strategy import _decide_with_decisions
from orbit_wars.heuristic.heuristic_overhaul.config import HeuristicConfig
from orbit_wars.mcts.token import LaunchToken
from orbit_wars.mcts.mcts_overhaul.features import extract_features, STATE_DIM
from orbit_wars.mcts.mcts_overhaul.dense_token import encode_dense_token, NUM_TOKENS
from orbit_wars.mcts.mcts_overhaul.config import MCTSOverhaulConfig


def get_closest_bucket(fraction: float, buckets: tuple[float, ...]) -> int:
	"""Find the index of the closest bucket via pure python loops."""
	return min(range(len(buckets)), key=lambda i: abs(buckets[i] - fraction))


def generate_game_data(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
	"""Plays a single game of heuristic self-play and extracts training data."""
	# Imported inside the worker process to prevent multiprocessing serialization issues on Linux forks
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
		policy_vec[0] = 1.0  # COMMIT is always chosen eventually

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

	try:
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
		if N == 0:
			# Edge case where agent took no actions or died instantly
			return np.empty((0, STATE_DIM), dtype=np.float32), np.empty((0, NUM_TOKENS), dtype=np.float32), np.empty(
				(0, 1), dtype=np.float32)

		states = np.array(states_list, dtype=np.float32)
		policies = np.array(policies_list, dtype=np.float32)
		values = np.full((N, 1), value, dtype=np.float32)

		return states, policies, values
	except Exception as e:
		print(f"\nGame generation failed for seed {seed}: {e}")
		return np.empty((0, STATE_DIM), dtype=np.float32), np.empty((0, NUM_TOKENS), dtype=np.float32), np.empty((0, 1),
		                                                                                                         dtype=np.float32)


def save_chunk(states_buf, policies_buf, values_buf, out_path: Path):
	"""Concatenates the buffer and flushes it to disk to protect system RAM."""
	if not states_buf:
		return None, 0
	S = np.concatenate(states_buf, axis=0)
	P = np.concatenate(policies_buf, axis=0)
	V = np.concatenate(values_buf, axis=0)

	if len(S) == 0:
		return None, 0

	# Use microsecond timestamp to prevent parallel file collisions
	run_id = int(time.time() * 1_000_000)
	file_path = out_path / f"dataset_{run_id}.npz"
	np.savez_compressed(file_path, states=S, policies=P, values=V)
	return file_path, len(S)


def main(args):
	out_path = Path(args.out_dir)
	out_path.mkdir(parents=True, exist_ok=True)

	print(f"Starting local bootstrap generation for {args.num_games} games...")
	print(f"Targeting {args.num_workers} parallel CPU threads.")
	print(f"Saving a new .npz chunk every {args.games_per_chunk} games to prevent RAM exhaustion.")

	start_time = time.time()

	# Pre-generate unique random seeds for the matches
	seeds = [int(uuid.uuid4().int % 1000000) for _ in range(args.num_games)]

	buffer_states = []
	buffer_policies = []
	buffer_values = []

	games_processed = 0
	files_saved = 0
	total_frames_saved = 0

	# Using ProcessPoolExecutor to map the matches across all CPU threads
	with concurrent.futures.ProcessPoolExecutor(max_workers=args.num_workers) as executor:
		# Submit all tasks and track their futures
		future_to_seed = {executor.submit(generate_game_data, seed): seed for seed in seeds}

		# As matches finish across threads, immediately process them
		for future in concurrent.futures.as_completed(future_to_seed):
			try:
				states, policies, values = future.result()
				if len(states) > 0:
					buffer_states.append(states)
					buffer_policies.append(policies)
					buffer_values.append(values)

				games_processed += 1

				if games_processed % 10 == 0:
					print(f"\rProcessed {games_processed}/{args.num_games} games...", end="", flush=True)

				# Flush to disk if RAM buffer reaches the target chunk size
				if len(buffer_states) >= args.games_per_chunk:
					print(f"\nFlushing {len(buffer_states)} games to disk...")
					_, frames = save_chunk(buffer_states, buffer_policies, buffer_values, out_path)
					files_saved += 1
					total_frames_saved += frames

					# Clear memory buffers
					buffer_states.clear()
					buffer_policies.clear()
					buffer_values.clear()

			except Exception as exc:
				print(f"\nGame thread generated an exception: {exc}")

	# Save any remaining games in the final buffer
	if buffer_states:
		print(f"\nFlushing final {len(buffer_states)} games to disk...")
		_, frames = save_chunk(buffer_states, buffer_policies, buffer_values, out_path)
		if frames > 0:
			files_saved += 1
			total_frames_saved += frames

	print(f"\n\n--- Generation Complete ---")
	print(f"Time Elapsed:  {time.time() - start_time:.2f} seconds")
	print(f"Games Played:  {games_processed}")
	print(f"Total Frames:  {total_frames_saved}")
	print(f"Files Saved:   {files_saved} chunks to '{out_path.absolute()}'")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Generate Kaggle Orbit Wars dataset via Local CPU Multiprocessing.")
	parser.add_argument("--num-games", type=int, default=1000, help="Total number of self-play games to simulate.")
	parser.add_argument("--out-dir", type=str, default="./data/nn_bootstrap",
	                    help="Directory to save the generated dataset chunks.")
	# Targets your exact CPU threads by default
	parser.add_argument("--num-workers", type=int, default=min(8, os.cpu_count() or 8),
	                    help="Number of CPU threads to use.")

	# 100 games * ~300 turns = ~30,000 frames.
	# At 14,401 tokens wide, this requires ~1.7 GB of RAM before compressing and flushing to disk. Very safe for 32GB system.
	parser.add_argument("--games-per-chunk", type=int, default=100,
	                    help="How many games to buffer in RAM before saving to a file.")

	args = parser.parse_args()
	main(args)