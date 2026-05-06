"""Local A/B harness: MCTS-enabled vs heuristic on N seeds.

Runs MCTS-enabled (configurable) vs heuristic (via main.py) for N seeds,
alternating who plays player 0 each pair to control for the seat-asymmetry
that biased the initial 3-seed sanity test (heuristic-vs-heuristic on
seeds 42/7/100 was 0W/2T/1L just from RNG, not algorithm).

Usage:
    uv run python -m tools.mcts_local_ab --seeds 20
    uv run python -m tools.mcts_local_ab --seeds 20 --turn-budget-ms 300

Output: rich console table + JSON file in /tmp/mcts_ab_results.json.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from kaggle_environments import make

from orbit_wars.mcts import MCTSConfig, mcts_agent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=20,
                    help="Number of seeds to test (default: 20)")
    ap.add_argument("--seed-start", type=int, default=0,
                    help="Starting seed value (default: 0)")
    ap.add_argument("--turn-budget-ms", type=float, default=300.0)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--fixed-k", type=int, default=8)
    ap.add_argument("--out", default="/tmp/mcts_ab_results.json")
    args = ap.parse_args()

    cfg = MCTSConfig(
        enabled=True,
        turn_budget_ms=args.turn_budget_ms,
        max_depth=args.max_depth,
        fixed_k_per_player=args.fixed_k,
    )

    def make_mcts():
        def _agent(obs):
            return mcts_agent(obs, cfg)
        return _agent

    print(f"=== MCTS local A/B: N={args.seeds} seeds, budget={args.turn_budget_ms}ms, depth={args.max_depth}, k={args.fixed_k} ===\n")
    started_total = time.perf_counter()

    # We pair each seed: one game with MCTS as P0, one with MCTS as P1.
    # This controls for the inherent seat asymmetry from env's RNG-state-
    # consumption pattern.
    results: list[dict] = []
    for i in range(args.seeds):
        seed = args.seed_start + i

        # Game A: MCTS as player 0, heuristic (main.py) as player 1
        env = make("orbit_wars", debug=True, configuration={"seed": seed})
        started = time.perf_counter()
        env.run([make_mcts(), "src/main.py"])
        elapsed_a = time.perf_counter() - started
        ra = env.steps[-1][0].reward, env.steps[-1][1].reward
        outcome_mcts_a = "WIN" if ra[0] > ra[1] else ("LOSS" if ra[0] < ra[1] else "TIE")

        # Game B: heuristic as player 0, MCTS as player 1 (same seed, swapped seats)
        env = make("orbit_wars", debug=True, configuration={"seed": seed})
        started = time.perf_counter()
        env.run(["src/main.py", make_mcts()])
        elapsed_b = time.perf_counter() - started
        rb = env.steps[-1][0].reward, env.steps[-1][1].reward
        # MCTS is P1 here — swap perspective
        outcome_mcts_b = "WIN" if rb[1] > rb[0] else ("LOSS" if rb[1] < rb[0] else "TIE")

        results.append({
            "seed": seed,
            "as_p0": outcome_mcts_a,
            "as_p1": outcome_mcts_b,
            "elapsed_a_s": round(elapsed_a, 1),
            "elapsed_b_s": round(elapsed_b, 1),
        })
        print(f"  seed={seed:>3}: as P0 → {outcome_mcts_a:<4} ({elapsed_a:.0f}s)   as P1 → {outcome_mcts_b:<4} ({elapsed_b:.0f}s)")

    # Aggregate
    n_games = 2 * len(results)
    wins = sum(1 for r in results for o in (r["as_p0"], r["as_p1"]) if o == "WIN")
    ties = sum(1 for r in results for o in (r["as_p0"], r["as_p1"]) if o == "TIE")
    losses = n_games - wins - ties
    winrate = wins / n_games if n_games else 0.0
    total_elapsed = time.perf_counter() - started_total

    print(f"\n=== AGGREGATE (paired seats, {n_games} games) ===")
    print(f"  MCTS wins:   {wins:>3}  ({winrate:.1%})")
    print(f"  Ties:        {ties:>3}")
    print(f"  Losses:      {losses:>3}")
    print(f"  Total time:  {total_elapsed:.0f}s")

    # Gate per design v2 §4 M2: local self-play winrate ≥ 50%
    print()
    if winrate >= 0.50:
        print(f"  ✓ M2 gate PASS (≥50% winrate vs heuristic)")
    else:
        print(f"  ✗ M2 gate FAIL ({winrate:.1%} < 50%) — debug ranking + value before M3")

    # Persist
    out_path = Path(args.out)
    out_path.write_text(json.dumps({
        "config": {
            "seeds": args.seeds,
            "turn_budget_ms": args.turn_budget_ms,
            "max_depth": args.max_depth,
            "fixed_k": args.fixed_k,
        },
        "aggregate": {
            "n_games": n_games,
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "winrate": winrate,
        },
        "per_seed": results,
        "total_elapsed_s": round(total_elapsed, 1),
    }, indent=2))
    print(f"\n  results saved → {out_path}")
    return 0 if winrate >= 0.50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
