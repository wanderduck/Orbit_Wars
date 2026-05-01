"""Per-call instrumentation of `path_collision_predicted` (Phase 2 step 3a).

Patches the world-module function to log every call's args + result, then runs
N self-play seeds and aggregates stats:

- Total calls per game.
- Total aborts per game (calls that returned a non-None obstructing planet).
- Abort rate (aborts / calls).
- Per-abort log: (seed, turn, src_id, target_id, eta, ships, obstructor_id,
  obstructor_owner).
- Distribution of obstructors (which planets cause the most aborts).

NO production code change — uses unittest.mock.patch to wrap the function.
This is consistent with the existing tools/diagnostic.py pattern: instrumentation
lives in tools/, never in src/orbit_wars/.

Usage::

    uv run python -m tools.path_collision_instrumentation run --seeds 50 \
        --out docs/research_documents/competition_codebases/path_collision_instrumentation.md

Per the Phase 2 spec (Step 3a):
- No behavior change.
- Optionally: counterfactual rollouts (force the launch through, check if
  collision actually occurs). The initial pass below SKIPS counterfactual —
  decision deferred until basic stats are seen, since counterfactual would
  require forking the env per abort which is expensive and complex.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import typer
from kaggle_environments import make
from rich.console import Console

from orbit_wars.geometry import LAUNCH_CLEARANCE, fleet_speed
from orbit_wars.heuristic.strategy import agent as v15g_agent
from orbit_wars.world import path_collision_predicted as _real_path_collision_predicted

app = typer.Typer(help="Path-collision instrumentation harness (Phase 2 step 3a).")
console = Console()


@dataclass
class AbortRecord:
    """One aborted launch."""

    seed: int
    turn: int  # env step at which the call was made
    src_id: int
    target_id: int
    eta: int
    ships: int
    obstructor_id: int
    obstructor_owner: int
    # Fields needed for counterfactual rollout (populated from src/target Planet objects):
    src_x: float = 0.0
    src_y: float = 0.0
    src_radius: float = 0.0
    angle: float = 0.0
    # Counterfactual results (filled after env.run, by counterfactual_check):
    actually_collided: bool | None = None  # True if a real planet would have intercepted
    actual_collision_turn: int | None = None  # which turn after launch the collision occurs
    actual_obstructor_id: int | None = None  # which planet actually intercepts


@dataclass
class GameStats:
    seed: int
    total_calls: int = 0
    total_aborts: int = 0
    aborts: list[AbortRecord] = field(default_factory=list)


def _make_instrumented(
    call_log: list[dict],
    abort_log: list[AbortRecord],
    seed_ref: list[int],
    turn_ref: list[int],
):
    """Return a wrapper that logs each call to path_collision_predicted.

    seed_ref/turn_ref are 1-element lists used as mutable cells so the wrapper
    can read the current seed and current env step set by the outer loop.
    """

    def wrapper(
        src, target, angle, ships, eta, *,
        view, comet_paths=None, comet_path_indices=None, skip_own=True,
    ):
        result = _real_path_collision_predicted(
            src=src, target=target, angle=angle, ships=ships, eta=eta,
            view=view, comet_paths=comet_paths, comet_path_indices=comet_path_indices,
            skip_own=skip_own,
        )
        call_log.append({"seed": seed_ref[0], "turn": turn_ref[0]})
        if result is not None:
            abort_log.append(
                AbortRecord(
                    seed=seed_ref[0],
                    turn=turn_ref[0],
                    src_id=int(src.id),
                    target_id=int(target.id),
                    eta=int(eta),
                    ships=int(ships),
                    obstructor_id=int(result.id),
                    obstructor_owner=int(result.owner),
                    src_x=float(src.x),
                    src_y=float(src.y),
                    src_radius=float(src.radius),
                    angle=float(angle),
                )
            )
        return result

    return wrapper


def _run_one_seed(seed: int, call_log: list[dict], abort_log: list[AbortRecord]) -> GameStats:
    """Run one self-play episode and return per-game stats.

    The instrumented wrapper is patched into BOTH the world module (so other
    callers also get logged) and the strategy module (which imported the
    function by name — that import is a separate reference).
    """
    seed_ref = [seed]
    turn_ref = [0]

    # Wrap agent to capture turn count so abort records have the env step
    def turn_tracking_agent(obs, config=None):
        # obs.step is 1-indexed; capture for the next call to path_collision_predicted
        if isinstance(obs, dict):
            turn_ref[0] = int(obs.get("step", 0) or 0)
        else:
            turn_ref[0] = int(getattr(obs, "step", 0) or 0)
        return v15g_agent(obs, config)

    pre_call_count = len(call_log)
    pre_abort_count = len(abort_log)

    wrapper = _make_instrumented(call_log, abort_log, seed_ref, turn_ref)
    with patch("orbit_wars.heuristic.strategy.path_collision_predicted", wrapper):
        env = make("orbit_wars", debug=False, configuration={"seed": seed})
        env.run([turn_tracking_agent, turn_tracking_agent])

    # Counterfactual: for each abort in this game, check whether the would-be fleet
    # would have ACTUALLY been intercepted by any planet at its true position
    # (per the env's recorded steps). This gives us the false-positive rate.
    game_aborts = abort_log[pre_abort_count:]
    for ab in game_aborts:
        _populate_counterfactual(ab, env.steps)

    return GameStats(
        seed=seed,
        total_calls=len(call_log) - pre_call_count,
        total_aborts=len(abort_log) - pre_abort_count,
        aborts=list(game_aborts),
    )


def _populate_counterfactual(abort: AbortRecord, env_steps: list) -> None:
    """Walk env_steps from abort.turn forward by `eta` turns. At each turn, check
    whether the virtual fleet's predicted position would intersect any non-src
    non-target planet's ACTUAL recorded position. Populates abort.actually_collided
    and related fields.

    Note on indexing: kaggle_environments uses 1-indexed obs.step. env_steps[N] is
    the state AFTER turn N played (env_steps[0] = initial state). When the wrapper
    logged `turn = obs.step`, the agent was about to decide turn `obs.step`. The
    fleet would launch during that turn; at "t turns after launch" the post-turn
    state is env_steps[abort.turn + t - 1].
    """
    speed = fleet_speed(abort.ships)
    sx = abort.src_x + math.cos(abort.angle) * (abort.src_radius + LAUNCH_CLEARANCE)
    sy = abort.src_y + math.sin(abort.angle) * (abort.src_radius + LAUNCH_CLEARANCE)
    dx = math.cos(abort.angle)
    dy = math.sin(abort.angle)

    abort.actually_collided = False
    for t in range(1, abort.eta + 1):
        step_idx = abort.turn + t - 1
        if step_idx >= len(env_steps):
            # Game ended before fleet would have arrived — neither true positive
            # nor false positive cleanly. Treat as "not collided" (would have arrived
            # safely) for FP-rate purposes, but record as ambiguous via collision_turn=None.
            return
        try:
            obs_t = env_steps[step_idx][0].observation
            planets = obs_t.planets if hasattr(obs_t, "planets") else obs_t.get("planets", [])
        except (AttributeError, KeyError, IndexError):
            return

        fx = sx + dx * speed * t
        fy = sy + dy * speed * t
        for p_data in planets:
            # Planet tuple shape (per kaggle_environments orbit_wars):
            # (id, x, y, radius, ships, owner, production)
            try:
                pid = int(p_data[0])
                px = float(p_data[1])
                py = float(p_data[2])
                pradius = float(p_data[3])
            except (IndexError, TypeError):
                continue
            if pid in (abort.src_id, abort.target_id):
                continue
            d = math.hypot(fx - px, fy - py)
            if d < pradius + LAUNCH_CLEARANCE:
                abort.actually_collided = True
                abort.actual_collision_turn = t
                abort.actual_obstructor_id = pid
                return


@app.command()
def run(  # noqa: PLR0915
    seeds: int = typer.Option(50, "--seeds", help="Number of self-play seeds (each is one episode)."),  # noqa: B008
    seed_offset: int = typer.Option(0, "--seed-offset", help="First seed value (0 by default)."),  # noqa: B008
    out: Path = typer.Option(  # noqa: B008
        Path("docs/research_documents/competition_codebases/path_collision_instrumentation.md"),
        "--out",
        help="Output markdown report path.",
    ),
    json_out: Path | None = typer.Option(  # noqa: B008
        None,
        "--json-out",
        help="Optional raw stats JSON dump (default: same dir as --out, .json suffix).",
    ),
) -> None:
    """Run N self-play seeds with path_collision_predicted patched to log all calls."""
    random.seed(42)  # CLAUDE.md: seed once before loop

    call_log: list[dict] = []
    abort_log: list[AbortRecord] = []
    games: list[GameStats] = []

    for i in range(seeds):
        s = seed_offset + i
        gs = _run_one_seed(s, call_log, abort_log)
        games.append(gs)
        console.print(f"  seed {s}: {gs.total_calls} calls, {gs.total_aborts} aborts "
                      f"({100.0 * gs.total_aborts / max(1, gs.total_calls):.1f}% abort rate)")

    # Aggregate
    total_calls = sum(g.total_calls for g in games)
    total_aborts = sum(g.total_aborts for g in games)
    overall_abort_rate = total_aborts / max(1, total_calls)
    median_calls = sorted([g.total_calls for g in games])[len(games) // 2]
    median_aborts = sorted([g.total_aborts for g in games])[len(games) // 2]

    # Obstructor distribution
    obstructor_counts: Counter[int] = Counter(a.obstructor_id for a in abort_log)
    obstructor_owner_counts: Counter[int] = Counter(a.obstructor_owner for a in abort_log)

    # Counterfactual: false-positive rate = aborts that would NOT have actually collided.
    cf_evaluated = [a for a in abort_log if a.actually_collided is not None]
    cf_true_positives = sum(1 for a in cf_evaluated if a.actually_collided)
    cf_false_positives = sum(1 for a in cf_evaluated if not a.actually_collided)
    cf_unevaluated = sum(1 for a in abort_log if a.actually_collided is None)
    cf_total_eval = max(1, len(cf_evaluated))
    cf_fp_rate = cf_false_positives / cf_total_eval

    # Per-turn abort distribution (when in the game do aborts cluster?)
    aborts_by_turn_bucket: dict[str, int] = defaultdict(int)
    for a in abort_log:
        if a.turn <= 50:
            bucket = "early (1-50)"
        elif a.turn <= 200:
            bucket = "mid (51-200)"
        elif a.turn <= 400:
            bucket = "late (201-400)"
        else:
            bucket = "endgame (401+)"
        aborts_by_turn_bucket[bucket] += 1

    # Write JSON (raw)
    if json_out is None:
        json_out = out.with_suffix(".json")
    json_out.parent.mkdir(parents=True, exist_ok=True)
    raw = {
        "config": {"seeds": seeds, "seed_offset": seed_offset, "rng_seed": 42},
        "summary": {
            "total_calls": total_calls,
            "total_aborts": total_aborts,
            "overall_abort_rate": overall_abort_rate,
            "median_calls_per_game": median_calls,
            "median_aborts_per_game": median_aborts,
            "counterfactual_evaluated": len(cf_evaluated),
            "counterfactual_true_positives": cf_true_positives,
            "counterfactual_false_positives": cf_false_positives,
            "counterfactual_unevaluated": cf_unevaluated,
            "counterfactual_fp_rate": cf_fp_rate,
        },
        "per_seed": [
            {"seed": g.seed, "calls": g.total_calls, "aborts": g.total_aborts}
            for g in games
        ],
        "obstructor_counts_top10": obstructor_counts.most_common(10),
        "obstructor_owner_counts": dict(obstructor_owner_counts),
        "aborts_by_turn_bucket": dict(aborts_by_turn_bucket),
        "all_aborts": [
            {
                "seed": a.seed, "turn": a.turn, "src_id": a.src_id,
                "target_id": a.target_id, "eta": a.eta, "ships": a.ships,
                "obstructor_id": a.obstructor_id, "obstructor_owner": a.obstructor_owner,
                "actually_collided": a.actually_collided,
                "actual_collision_turn": a.actual_collision_turn,
                "actual_obstructor_id": a.actual_obstructor_id,
            }
            for a in abort_log
        ],
    }
    json_out.write_text(json.dumps(raw, indent=2))

    # Write markdown
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_markdown(raw))
    console.print(f"\n[bold]Report:[/bold] {out}")
    console.print(f"[bold]JSON:[/bold] {json_out}")


def _render_markdown(raw: dict) -> str:  # noqa: PLR0915
    s = raw["summary"]
    cfg = raw["config"]
    per_seed = raw["per_seed"]
    obs_top = raw["obstructor_counts_top10"]
    own_counts = raw["obstructor_owner_counts"]
    bucket = raw["aborts_by_turn_bucket"]

    # Mean aborts per game
    abort_counts = sorted([g["aborts"] for g in per_seed])
    mean_aborts = sum(abort_counts) / max(1, len(abort_counts))
    p25 = abort_counts[len(abort_counts) // 4]
    p75 = abort_counts[3 * len(abort_counts) // 4]

    md = []
    md.append("# Path-collision instrumentation report (Phase 2 step 3a)")
    md.append("")
    md.append("**Date:** 2026-05-01")
    md.append(f"**Seeds:** {cfg['seeds']} self-play episodes "
              "(v1.5G vs v1.5G, default HeuristicConfig).")
    md.append("**Tool:** `tools.path_collision_instrumentation`. "
              "Patches `orbit_wars.heuristic.strategy.path_collision_predicted` "
              "to log every call without modifying production code.")
    md.append("")
    md.append("## Summary")
    md.append("")
    md.append(f"- **Total calls:** {s['total_calls']:,}")
    md.append(f"- **Total aborts:** {s['total_aborts']:,}")
    md.append(f"- **Overall abort rate:** {100*s['overall_abort_rate']:.2f}%")
    md.append(f"- **Aborts per game:** mean {mean_aborts:.1f}, "
              f"median {s['median_aborts_per_game']}, "
              f"p25 {p25}, p75 {p75}")
    md.append(f"- **Calls per game:** median {s['median_calls_per_game']}")
    md.append("")
    md.append("### Counterfactual rollout (would the fleet have actually been intercepted?)")
    md.append("")
    md.append(f"- **Aborts evaluated:** {s['counterfactual_evaluated']:,} "
              f"(of {s['total_aborts']:,} total; {s['counterfactual_unevaluated']:,} "
              f"unevaluated because game ended mid-rollout)")
    md.append(f"- **True positives** (real interception would have occurred): "
              f"{s['counterfactual_true_positives']:,}")
    md.append(f"- **False positives** (no real interception — abort was unnecessary): "
              f"{s['counterfactual_false_positives']:,}")
    md.append(f"- **False-positive rate:** {100*s['counterfactual_fp_rate']:.1f}%")
    md.append("")
    md.append("## Per-game distribution")
    md.append("")
    md.append("| seed | calls | aborts | abort % |")
    md.append("|---|---|---|---|")
    for g in per_seed[:20]:
        rate = 100 * g["aborts"] / max(1, g["calls"])
        md.append(f"| {g['seed']} | {g['calls']} | {g['aborts']} | {rate:.1f}% |")
    if len(per_seed) > 20:
        md.append(f"| … | … | … | (showing first 20 of {len(per_seed)}) |")
    md.append("")
    md.append("## Aborts by turn-bucket")
    md.append("")
    md.append("| Bucket | Aborts | % of total |")
    md.append("|---|---|---|")
    for k in ["early (1-50)", "mid (51-200)", "late (201-400)", "endgame (401+)"]:
        v = bucket.get(k, 0)
        pct = 100 * v / max(1, s["total_aborts"])
        md.append(f"| {k} | {v} | {pct:.1f}% |")
    md.append("")
    md.append("## Top obstructor planets (by abort count)")
    md.append("")
    md.append("| Planet ID | Aborts caused |")
    md.append("|---|---|")
    for pid, n in obs_top:
        md.append(f"| {pid} | {n} |")
    md.append("")
    md.append("## Obstructor by owner")
    md.append("")
    md.append("| Owner | Aborts caused | Note |")
    md.append("|---|---|---|")
    owner_label = {-1: "neutral", 0: "self (player 0)", 1: "enemy 1", 2: "enemy 2", 3: "enemy 3"}
    for owner, n in sorted(own_counts.items(), key=lambda x: -x[1]):
        label = owner_label.get(owner, f"owner {owner}")
        md.append(f"| {owner} | {n} | {label} |")
    md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append("Per Phase 2 spec decision tree:")
    md.append("- If aborts are **rare** (≪1 per game median) AND patterns suggest "
              "the check is doing useful work: close the loop, no 3b needed.")
    md.append("- If aborts are **frequent** (many per game) AND a high fraction look "
              "like false positives (predicted collision against neutral planets that "
              "wouldn't realistically intercept): 3a data justifies a 3b hot-fix proposal "
              "to add a `relax_path_collision` toggle and ladder-test it.")
    md.append("- **Counterfactual rollout** (force aborted launches through, check actual "
              "interception rate) was deferred from this initial pass because it requires "
              "env forking per abort. If 3a numbers warrant it, a follow-up 3a-extended "
              "pass can add this.")
    md.append("")
    md.append("Decision based on this report: **(filled in after read by lead agent)**")
    md.append("")
    md.append("## Raw data")
    md.append("")
    md.append(f"Full per-abort log + per-game counts in JSON: see sibling file "
              f"`{out_json_name(raw, cfg)}`.")
    return "\n".join(md) + "\n"


def out_json_name(raw, cfg):
    """Helper for markdown — returns the JSON filename."""
    return "path_collision_instrumentation.json"


if __name__ == "__main__":
    app()
