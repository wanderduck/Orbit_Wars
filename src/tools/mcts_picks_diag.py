"""Diagnostic: capture which root variant MCTS picks each turn.

The M2 A/B (10 seeds × 2 seats = 20 games) returned 0 wins. Variant 0 at
the root IS the heuristic action (per `ranked_actions_with_heuristic`),
so 0/20 means MCTS systematically deviates from the heuristic into worse
variants. This script confirms WHICH variant by capturing each turn's
``our_action_idx`` from search()'s debug dict.

Run:
    uv run python -m tools.mcts_picks_diag --seeds 0,1 --budget-ms 200

Variant legend (root pre-population, see ranking.py):
  0 = full heuristic action (variant 0 = `get_heuristic_action_for(...)`)
  1 = HOLD (empty action list — wait this turn)
  2..k = drop-one launch variants from the lightweight nearest-target ranker
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from kaggle_environments import make

from orbit_wars.mcts import MCTSConfig
from orbit_wars.mcts.agent import mcts_agent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", default="0",
                    help="Comma-separated seed list (default: 0)")
    ap.add_argument("--budget-ms", type=float, default=200.0)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--fixed-k", type=int, default=8)
    ap.add_argument(
        "--fpu-c", type=float, default=0.5,
        help="First-Play Urgency value for unvisited variants (default 0.5). "
        "Higher = more exploration of unvisited; tune above heuristic's typical "
        "mean value (~0.55) to enable variant exploration.",
    )
    ap.add_argument("--out", default="/tmp/mcts_picks_diag.json")
    args = ap.parse_args()

    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    cfg = MCTSConfig(
        enabled=True,
        turn_budget_ms=args.budget_ms,
        max_depth=args.max_depth,
        fixed_k_per_player=args.fixed_k,
        fpu_c=args.fpu_c,
    )

    all_results: list[dict] = []

    for seed in seeds:
        # Capture per-turn debug. The harness uses a closure with a list
        # so each turn's debug appends.
        per_turn: list[dict] = []

        def capture_agent(obs):
            d: dict = {}
            action = mcts_agent(obs, cfg, debug=d)
            per_turn.append(dict(d))  # snapshot
            return action

        env = make("orbit_wars", debug=True, configuration={"seed": seed})
        env.run([capture_agent, "src/main.py"])

        # Outcome from MCTS-as-P0 perspective
        last = env.steps[-1]
        outcome = (
            "WIN" if last[0].reward > last[1].reward
            else "LOSS" if last[0].reward < last[1].reward
            else "TIE"
        )

        # Aggregate variant-pick distribution
        idx_counter: Counter[int] = Counter()
        fallback_counter: Counter[str] = Counter()
        n_zero_action_turns = 0  # turns where our action_list is empty

        for d in per_turn:
            if "fallback" in d:
                fallback_counter[d["fallback"]] += 1
                continue
            idx = d.get("our_action_idx")
            if idx is None:
                continue
            idx_counter[idx] += 1

        result = {
            "seed": seed,
            "outcome": outcome,
            "n_turns": len(per_turn),
            "variant_pick_distribution": dict(sorted(idx_counter.items())),
            "fallbacks": dict(fallback_counter),
        }
        all_results.append(result)

        # Pretty print
        print(f"\n=== Seed {seed} → {outcome} ({len(per_turn)} turns) ===")
        for idx, count in sorted(idx_counter.items()):
            label = (
                "heuristic" if idx == 0
                else "HOLD" if idx == 1
                else f"drop-one #{idx-1}"
            )
            pct = 100.0 * count / len(per_turn) if per_turn else 0.0
            print(f"  variant {idx} ({label:>15}): {count:>4} turns ({pct:5.1f}%)")
        if fallback_counter:
            print(f"  fallbacks: {dict(fallback_counter)}")

    # Persist
    Path(args.out).write_text(json.dumps(all_results, indent=2))
    print(f"\n  results saved → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
