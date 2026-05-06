"""Token generator — converts a SimState + player_id into a ranked LaunchToken list.

Per docs/research_documents/2026-05-06-mcts-option2-tokens-design.md §5.1:

    state, player_id
            |
            v
    _simstate_to_env_dict(state) + obs_dict["player"] = player_id
            |
            v
    heuristic.decide_with_decisions(obs_dict, None) -> (moves, decisions)
            |
            v
    For each decision in decisions (in heuristic-rank order):
      chosen_fraction = decision.ships / src.ships
      Pick `tokens_per_decision` buckets nearest chosen_fraction
      Emit one LaunchToken per chosen bucket
            |
            v
    Prepend LaunchToken.COMMIT at index 0
            |
            v
    return list[LaunchToken]

Long-tail extender (extend_with_long_tail) is provided but OFF by default per
design Risk 1 mitigation. Enabling it adds (sources × non-self-targets ×
buckets) tokens — ~530 worst-case — sorted by L2 distance from src to target.

This module is the OPTION 2 analogue of `ranking.py:ranked_actions_for`. Both
files coexist: `ranking.py` is used when `cfg.use_token_variants=False` (the
legacy compound-variant path); this module is used when True.
"""

from __future__ import annotations

import math

from orbit_wars.heuristic.strategy import decide_with_decisions
from orbit_wars.sim.state import SimState
from orbit_wars.sim.validator import _simstate_to_env_dict

from .config import MCTSConfig
from .token import LaunchToken

__all__ = ["generate_ranked_tokens", "extend_with_long_tail"]


def generate_ranked_tokens(
    state: SimState, player_id: int, cfg: MCTSConfig
) -> list[LaunchToken]:
    """Return ranked tokens for `player_id` at `state`.

    Index 0 is always ``LaunchToken.COMMIT`` (the "stop launching" sentinel —
    selecting it advances the simulator). Indices 1..N are heuristic-derived,
    ordered first by LaunchDecision rank, then by bucket-distance from the
    heuristic's chosen ship fraction.

    Per design §5.2, COMMIT is at index 0 (highest prior) so PW's first
    consideration at low visit counts is "do nothing vs the heuristic's best
    launch" — exactly the comparison we want at shallow searches.

    Cost: one heuristic call (~10-20ms) + bucket arithmetic (~µs). Cached at
    the MCTSNode level so re-visited nodes pay zero ranking cost.

    Long-tail tokens (sources × non-self-targets × buckets minus the prior)
    can be appended via :func:`extend_with_long_tail` when PW asks for k >
    len(prior). This is OFF by default; enable via `cfg.long_tail_enabled`.
    """
    tokens: list[LaunchToken] = [LaunchToken.COMMIT]

    # Run the full heuristic from `player_id`'s perspective to get the prior.
    obs_dict = _simstate_to_env_dict(state)
    obs_dict["player"] = player_id
    obs_dict["remainingOverageTime"] = 60.0  # arbitrary; heuristic doesn't read it
    _moves, decisions = decide_with_decisions(obs_dict, None)

    if not decisions:
        # Heuristic chose to launch nothing — only COMMIT is meaningful.
        return tokens

    n_buckets = len(cfg.ship_fraction_buckets)
    tokens_per_dec = max(1, min(cfg.tokens_per_decision, n_buckets))

    for decision in decisions:
        src = state.planet_by_id(decision.src_id)
        if src is None or src.ships <= 0:
            # Heuristic ranked a launch from an empty / nonexistent source —
            # shouldn't happen, but skip defensively to keep the prior valid.
            continue
        chosen_fraction = decision.ships / max(src.ships, 1)
        # Sort buckets by absolute distance from the heuristic's chosen
        # fraction. The closest bucket is the "heuristic bucket"; the next
        # closest are the perturbation candidates.
        bucket_order = sorted(
            range(n_buckets),
            key=lambda i: abs(cfg.ship_fraction_buckets[i] - chosen_fraction),
        )
        for bucket_idx in bucket_order[:tokens_per_dec]:
            tokens.append(
                LaunchToken(
                    src_planet_id=decision.src_id,
                    target_planet_id=decision.target_id,
                    ship_fraction_bucket=bucket_idx,
                )
            )

    return tokens


def extend_with_long_tail(
    tokens: list[LaunchToken],
    state: SimState,
    player_id: int,
    cfg: MCTSConfig,
) -> list[LaunchToken]:
    """Append long-tail tokens (all owned-source × any-target × all-buckets
    minus tokens already in the list) sorted by L2 distance from src to target.

    Idempotent — calling twice produces the same list as calling once. This
    matters because the search may invoke long-tail expansion multiple times
    as PW grows.

    Per design Risk 1 / §2.3: long-tail is OFF by default
    (``cfg.long_tail_enabled=False``); this function is a no-op in that case.
    Asymptotic completeness only matters at infinite budget; at our 700ms
    budget the heuristic-derived prior dominates.

    NOTE: long-tail enumeration is ``O(n_sources × n_targets × n_buckets)``;
    at 6 sources × 28 planets × 4 buckets = 672 candidates worst case.
    """
    if not cfg.long_tail_enabled:
        return tokens

    existing: set[tuple[int, int, int]] = {
        (t.src_planet_id, t.target_planet_id, t.ship_fraction_bucket)
        for t in tokens
        if not t.is_commit()
    }

    owned_sources = [p for p in state.planets if p.owner == player_id and p.ships > 0]
    candidates: list[tuple[float, LaunchToken]] = []
    for src in owned_sources:
        for tgt in state.planets:
            if tgt.id == src.id:
                continue
            dx, dy = tgt.x - src.x, tgt.y - src.y
            dist = math.sqrt(dx * dx + dy * dy)
            for bucket_idx in range(len(cfg.ship_fraction_buckets)):
                key = (src.id, tgt.id, bucket_idx)
                if key in existing:
                    continue
                candidates.append(
                    (dist, LaunchToken(src.id, tgt.id, bucket_idx))
                )

    # Sort by distance ascending — closer targets are more likely to be
    # captureable, hence higher-prior in the long tail.
    candidates.sort(key=lambda pair: pair[0])
    tokens.extend(tok for _dist, tok in candidates)
    return tokens
