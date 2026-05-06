"""Local smoke test for Plan A 4P retool — no Modal, no $.

Runs a single candidate (HeuristicConfig.default()) through the new
evaluate_fitness_local with a small game budget (~5 4P games) and prints
the result. ~1 minute runtime. Use this before launching the Modal sweep
to confirm the 4P pipeline works end-to-end.

Usage:
    uv run python -m tools.smoke_4p_local
    uv run python -m tools.smoke_4p_local --games 10  # more games for tighter signal
    uv run python -m tools.smoke_4p_local --with-archive  # includes a fake archive entry

Expected output: a result dict with sanity_pass=True, fitness in [-1, +1],
and per_opp = {"4p_graduated": <same as fitness>}. If sanity_pass=False
the smoke test failed — check sanity_winrates for which opponent got
< 0.91 winrate.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import fields

from orbit_wars.heuristic.config import HeuristicConfig
from tools.modal_tuner import evaluate_fitness_local


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--games", type=int, default=5,
                    help="Number of 4P fitness games (default: 5)")
    ap.add_argument("--sanity-games", type=int, default=3,
                    help="Sanity games per opponent (default: 3)")
    ap.add_argument("--with-archive", action="store_true",
                    help="Include a fake archive entry to exercise mixed opponents")
    args = ap.parse_args()

    cfg_dict = {
        f.name: getattr(HeuristicConfig.default(), f.name)
        for f in fields(HeuristicConfig)
    }

    archive_opponents = None
    if args.with_archive:
        # Fake archive entry: copy of default with min_launch tweaked
        archive_cfg = dict(cfg_dict)
        archive_cfg["min_launch"] = 30
        archive_opponents = [
            {"name": "smoke_archive_test", "cfg_dict": archive_cfg},
        ]

    print("=== Plan A 4P retool — local smoke ===")
    print(f"  games         : {args.games}")
    print(f"  sanity games  : {args.sanity_games}")
    print(f"  archive       : {'1 fake entry' if args.with_archive else 'none (all-starter opponents)'}")
    print()

    started = time.time()
    result = evaluate_fitness_local(
        cfg_dict=cfg_dict,
        candidate_id=0,
        generation=0,
        sanity_n_per_opponent=args.sanity_games,
        fitness_n_per_opponent=args.games,
        sanity_threshold=0.91,
        archive_opponents=archive_opponents,
    )
    elapsed = time.time() - started

    print(f"=== Result (wall clock {elapsed:.1f}s) ===")
    print(json.dumps(result, indent=2))

    if not result["sanity_pass"]:
        print("\n⚠️  SANITY FAILED — candidate didn't beat sanity opponents at threshold 0.91.")
        print("   Inspect sanity_winrates above. Fix the agent or lower the threshold.")
        return 1

    print(f"\n✓ Smoke OK — fitness {result['fitness']:+.4f} in {elapsed:.1f}s")
    print("\nNext steps:")
    print(f"  Task 7: launch the iteration sweep on Modal")
    print(f"          uv run modal run src/tools/modal_tuner.py --iteration --confirm-cost")
    print(f"          (~$50 estimated, ~10-20 min wall clock)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
