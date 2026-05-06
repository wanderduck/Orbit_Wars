"""Local paired-seat A/B harness: heuristic_overhaul vs current src/main.py.

Per CLAUDE.md notes on env RNG-state consumption (`phase2_step4_findings.md`):

  - Same `configuration={'seed': N}` produces DIFFERENT outcomes depending on
    where in the random stream the game runs, because env internals consume
    Python's global random state between turns.
  - Cross-script comparisons are INVALID — must be run in one script with
    matched random-stream positions.
  - Paired seats per seed control for env's seat asymmetry.

This harness runs each seed twice (overhaul as P0 then as P1) inside one
Python process so the environment RNG stream is consistent. Reports the
overhaul's paired-seat win rate.

Usage:
    uv run python -m tools.overhaul_local_ab --seeds 5            # smoke
    uv run python -m tools.overhaul_local_ab --seeds 50           # full A/B (~25 min)
    uv run python -m tools.overhaul_local_ab --seeds 50 --out /tmp/ab.json

PREREQUISITE: the overhaul must be importable. As of 2026-05-06 it is NOT —
see chat report for the three import bugs that need fixing first
(relative-import depth in strategy.py; modal_tuner.py's wrong absolute
imports; and the tools.heuristic_tuner_param_space path mismatch). Once
those are cleaned up, this harness is ready to run.

If the user has restructured the overhaul package layout, change the
OVERHAUL_AGENT_IMPORT line below to match.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

# Adjust this if the overhaul moves to a different package path.
OVERHAUL_AGENT_IMPORT = "orbit_wars.heuristic.heuristic_overhaul.strategy"
OVERHAUL_CONFIG_IMPORT = "orbit_wars.heuristic.heuristic_overhaul.config"


def _load_overhaul_agent():
    """Late import so import errors surface as a clear message at runtime,
    not at module-load time. The overhaul currently has relative-import bugs
    (see chat report) that prevent it from importing successfully."""
    import importlib
    try:
        strategy_mod = importlib.import_module(OVERHAUL_AGENT_IMPORT)
        config_mod = importlib.import_module(OVERHAUL_CONFIG_IMPORT)
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"\n  ERROR: cannot import overhaul ({exc}).\n"
            f"  This harness expects the overhaul to be importable as\n"
            f"    {OVERHAUL_AGENT_IMPORT}.agent\n"
            f"    {OVERHAUL_CONFIG_IMPORT}.HeuristicConfig\n"
            f"  See chat report for the relative-import bug in the overhaul's\n"
            f"  strategy.py — it uses 'from ..geometry import' but should be\n"
            f"  'from ...geometry import' (or absolute imports).\n"
        ) from exc
    return strategy_mod.agent, config_mod.HeuristicConfig


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=5,
                    help="Number of seeds to test (default 5 for smoke). "
                    "Each seed runs TWO games (paired seats), so total games = 2×seeds.")
    ap.add_argument("--seed-start", type=int, default=0,
                    help="Starting seed value (default 0).")
    ap.add_argument("--out", default="/tmp/overhaul_ab_results.json",
                    help="Where to write JSON results.")
    ap.add_argument("--current-agent", default="src/main.py",
                    help="Path to the 'current production' agent — defaults to "
                    "src/main.py (the v1.5G baseline). The overhaul is the "
                    "OTHER agent in each game.")
    args = ap.parse_args()

    overhaul_agent, OverhaulConfig = _load_overhaul_agent()
    overhaul_cfg_default = OverhaulConfig.default()

    def make_overhaul():
        """Return a fresh closure each time so env doesn't share state across
        the two paired games (env.run reuses the agent function — closures
        with module-level caches would cross-contaminate)."""
        def _agent(obs):
            return overhaul_agent(obs, overhaul_cfg_default)
        return _agent

    # Late import of kaggle_environments so the import-error path above
    # surfaces FAST without paying the kaggle import cost.
    from kaggle_environments import make

    print(f"=== Overhaul vs current A/B: N={args.seeds} seeds (paired seats) ===")
    print(f"  current agent: {args.current_agent}")
    print(f"  overhaul:      {OVERHAUL_AGENT_IMPORT}.agent (default cfg)")
    print()

    started_total = time.perf_counter()
    results: list[dict] = []
    n_with_error = 0

    for i in range(args.seeds):
        seed = args.seed_start + i

        # Game A: overhaul as P0, current as P1
        env = make("orbit_wars", debug=True, configuration={"seed": seed})
        started = time.perf_counter()
        try:
            env.run([make_overhaul(), args.current_agent])
            elapsed_a = time.perf_counter() - started
            ra0, ra1 = env.steps[-1][0].reward, env.steps[-1][1].reward
            outcome_overhaul_a = (
                "WIN" if ra0 > ra1 else ("LOSS" if ra0 < ra1 else "TIE")
            )
            n_turns_a = len(env.steps) - 1
        except Exception as exc:
            elapsed_a = time.perf_counter() - started
            outcome_overhaul_a = f"ERROR:{type(exc).__name__}"
            n_turns_a = 0
            n_with_error += 1

        # Game B: current as P0, overhaul as P1 (same seed, swapped seats)
        env = make("orbit_wars", debug=True, configuration={"seed": seed})
        started = time.perf_counter()
        try:
            env.run([args.current_agent, make_overhaul()])
            elapsed_b = time.perf_counter() - started
            rb0, rb1 = env.steps[-1][0].reward, env.steps[-1][1].reward
            outcome_overhaul_b = (
                "WIN" if rb1 > rb0 else ("LOSS" if rb1 < rb0 else "TIE")
            )
            n_turns_b = len(env.steps) - 1
        except Exception as exc:
            elapsed_b = time.perf_counter() - started
            outcome_overhaul_b = f"ERROR:{type(exc).__name__}"
            n_turns_b = 0
            n_with_error += 1

        results.append({
            "seed": seed,
            "as_p0": outcome_overhaul_a,
            "as_p1": outcome_overhaul_b,
            "n_turns_a": n_turns_a,
            "n_turns_b": n_turns_b,
            "elapsed_a_s": round(elapsed_a, 1),
            "elapsed_b_s": round(elapsed_b, 1),
        })
        print(f"  seed={seed:>3}: as P0 → {outcome_overhaul_a:<14}({n_turns_a:>3}t,{elapsed_a:>4.0f}s)"
              f"   as P1 → {outcome_overhaul_b:<14}({n_turns_b:>3}t,{elapsed_b:>4.0f}s)")

    # Aggregate
    n_games = 2 * len(results)
    outcome_counter: Counter[str] = Counter()
    for r in results:
        outcome_counter[r["as_p0"]] += 1
        outcome_counter[r["as_p1"]] += 1

    wins = outcome_counter.get("WIN", 0)
    ties = outcome_counter.get("TIE", 0)
    losses = outcome_counter.get("LOSS", 0)
    errors = sum(c for o, c in outcome_counter.items() if o.startswith("ERROR"))
    winrate = wins / max(1, n_games - errors)
    total_elapsed = time.perf_counter() - started_total

    print(f"\n=== AGGREGATE ({n_games} games, {n_games - errors} non-error) ===")
    print(f"  Overhaul wins:    {wins:>3}  ({winrate:.1%} of non-error)")
    print(f"  Ties:             {ties:>3}")
    print(f"  Losses:           {losses:>3}")
    print(f"  Errors:           {errors:>3}")
    print(f"  Total time:       {total_elapsed:.0f}s")

    # Decision threshold guidance (per chat: ≥55% paired wr to be even
    # marginally interesting; ≥60% to consider switching default).
    print()
    if errors > 0:
        print(f"  ⚠ {errors} errored games — investigate before relying on the winrate")
    elif winrate >= 0.60:
        print(f"  ✓ Overhaul ≥60% paired wr → strong evidence of improvement; "
              f"queue ladder submission")
    elif winrate >= 0.55:
        print(f"  ~ Overhaul {winrate:.1%} paired wr → marginal; possibly worth a "
              f"ladder submission, but ladder noise (±100 μ) may dominate")
    elif winrate <= 0.45:
        print(f"  ✗ Overhaul ≤45% paired wr → regression vs current; "
              f"do NOT submit to ladder until investigated")
    else:
        print(f"  · Overhaul {winrate:.1%} paired wr → essentially a wash; "
              f"the overhaul is not clearly better OR worse locally")

    out_path = Path(args.out)
    out_path.write_text(json.dumps({
        "config": {
            "seeds": args.seeds,
            "seed_start": args.seed_start,
            "current_agent": args.current_agent,
            "overhaul_module": OVERHAUL_AGENT_IMPORT,
        },
        "aggregate": {
            "n_games": n_games,
            "n_non_error": n_games - errors,
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "errors": errors,
            "winrate_non_error": winrate,
        },
        "per_seed": results,
        "total_elapsed_s": round(total_elapsed, 1),
    }, indent=2))
    print(f"\n  results saved → {out_path}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
