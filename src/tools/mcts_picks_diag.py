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
        help="First-Play Urgency value for unvisited variants (default 0.5).",
    )
    ap.add_argument(
        "--use-token-variants", action="store_true",
        help="Enable option-2 single-launch-token search (default: legacy "
        "compound-variant). With this flag, the diagnostic logs committed "
        "token sequences per turn instead of variant indices.",
    )
    ap.add_argument(
        "--max-launches-per-turn", type=int, default=4,
        help="Per-env-turn launch sub-tree cap (option-2 only).",
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
        use_token_variants=args.use_token_variants,
        max_launches_per_turn=args.max_launches_per_turn,
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

        # Aggregate distribution. Two debug shapes:
        #  - Legacy (use_token_variants=False): debug has "our_action_idx" int.
        #    Aggregate by variant index (0=heuristic, 1=HOLD, 2..k=drop-one).
        #  - Token (use_token_variants=True): debug has "our_token_indices" list.
        #    Aggregate by sequence "type" — distinct sequences and per-sequence
        #    counts, plus pick-count distribution.
        idx_counter: Counter[int] = Counter()  # legacy mode
        seq_counter: Counter[tuple[int, ...]] = Counter()  # token mode
        pick_count_counter: Counter[int] = Counter()  # token mode
        fallback_counter: Counter[str] = Counter()

        for d in per_turn:
            if "fallback" in d:
                fallback_counter[d["fallback"]] += 1
                continue
            if args.use_token_variants:
                seq = tuple(d.get("our_token_indices", []))
                seq_counter[seq] += 1
                pick_count_counter[len(seq)] += 1
            else:
                idx = d.get("our_action_idx")
                if idx is None:
                    continue
                idx_counter[idx] += 1

        result: dict = {
            "seed": seed,
            "outcome": outcome,
            "n_turns": len(per_turn),
            "fallbacks": dict(fallback_counter),
            "use_token_variants": args.use_token_variants,
        }
        if args.use_token_variants:
            # Convert tuple keys to JSON-friendly strings ("[1,5,3]")
            result["token_sequence_distribution"] = {
                str(list(seq)): cnt for seq, cnt in seq_counter.most_common(20)
            }
            result["pick_count_distribution"] = dict(sorted(pick_count_counter.items()))
            result["distinct_sequences"] = len(seq_counter)
        else:
            result["variant_pick_distribution"] = dict(sorted(idx_counter.items()))
        all_results.append(result)

        # Pretty print
        print(f"\n=== Seed {seed} → {outcome} ({len(per_turn)} turns) ===")
        if args.use_token_variants:
            print(f"  distinct sequences:    {len(seq_counter)}")
            print(f"  pick count distribution: {dict(sorted(pick_count_counter.items()))}")
            print(f"  top sequences:")
            for seq, cnt in seq_counter.most_common(5):
                pct = 100.0 * cnt / len(per_turn) if per_turn else 0.0
                # Decode: 0 = COMMIT, 1+ = heuristic-derived tokens
                label = ("[]" if not seq else
                         f"{list(seq)}")
                print(f"    {label:<35}  {cnt:>4} turns ({pct:5.1f}%)")
        else:
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
