"""Dense token encoding for Neural Network policy logits.

The legacy token_id uses a sparse bitmask. We need a dense [0, N-1] range
for the NN's final Linear layer.
"""

from __future__ import annotations
from orbit_wars.mcts.token import LaunchToken

MAX_PLANETS = 60
NUM_BUCKETS = 5
NUM_TOKENS = 1 + (MAX_PLANETS * MAX_PLANETS * NUM_BUCKETS)


def encode_dense_token(token: LaunchToken) -> int:
	"""Map a LaunchToken to a continuous index in [0, NUM_TOKENS-1]."""
	if token.is_commit():
		return 0

	s = token.src_planet_id
	t = token.target_planet_id
	b = token.ship_fraction_bucket

	# Safe guard
	if s >= MAX_PLANETS or t >= MAX_PLANETS or b >= NUM_BUCKETS:
		return 0  # Fallback to COMMIT if out of bounds

	return 1 + b + (t * NUM_BUCKETS) + (s * NUM_BUCKETS * MAX_PLANETS)


def decode_dense_token(idx: int) -> LaunchToken:
	"""Map a dense index back to a LaunchToken."""
	if idx == 0:
		return LaunchToken.COMMIT

	idx -= 1
	b = idx % NUM_BUCKETS
	idx //= NUM_BUCKETS
	t = idx % MAX_PLANETS
	s = idx // MAX_PLANETS

	return LaunchToken(src_planet_id=s, target_planet_id=t, ship_fraction_bucket=b)
