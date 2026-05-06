"""Performance probe: measure inject + env.step() throughput for Path C-env decision.

Runs a real episode to get a representative mid-game state, then times N
iterations of `inject_state_and_step()` to measure per-rollout-step cost.
Predicts MCTS rollouts-per-turn at the standard 700ms budget.

If actual throughput >= ~300 rollouts/turn at depth 10, Path C-env is viable
without needing the custom Python simulator. If <100, Path C-original is forced
earlier than expected.

Usage:
    uv run python -m tools.sim_perf_probe --iters 200 --depth 10
"""

from __future__ import annotations

import time
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


@app.command()
def main(
    iters: int = typer.Option(200, "--iters", help="Number of inject+step iterations to time."),
    depth: int = typer.Option(10, "--depth", help="MCTS rollout depth (steps per rollout)."),
    seed: int = typer.Option(7, "--seed", help="Episode seed for the source state."),
    source_step: int = typer.Option(50, "--source-step", help="Step in the source episode to extract from."),
    budget_ms: float = typer.Option(700.0, "--budget-ms", help="MCTS turn budget in milliseconds."),
) -> None:
    """Measure inject+step performance and predict MCTS rollouts/turn."""
    from kaggle_environments import make

    from orbit_wars.sim.validator import (
        extract_state_and_actions,
        inject_state_and_step,
    )

    console.print(f"[cyan]Running source episode (seed={seed}) to extract state at step {source_step}[/cyan]")
    env = make("orbit_wars", debug=True, configuration={"seed": seed})
    env.run(["random", "random"])
    if source_step >= len(env.steps):
        console.print(f"[red]Episode only has {len(env.steps)} steps; using step {len(env.steps) // 2}[/red]")
        source_step = len(env.steps) // 2
    sim_state, actions = extract_state_and_actions(env, source_step)
    console.print(f"  state has {len(sim_state.planets)} planets, {len(sim_state.fleets)} fleets, "
                  f"{len(sim_state.comet_groups)} comet group(s)")

    # Warm up (first inject does extra import / module init)
    _ = inject_state_and_step(sim_state, actions)

    console.print(f"\n[cyan]Timing {iters} iterations of inject + step[/cyan]")
    t0 = time.perf_counter()
    for _ in range(iters):
        _ = inject_state_and_step(sim_state, actions)
    elapsed = time.perf_counter() - t0

    per_iter_ms = (elapsed / iters) * 1000
    rollout_step_cost_ms = per_iter_ms  # one inject+step is one rollout step (or one inject for K=1)

    # MCTS-style rollout: 1 inject (at root of the rollout) + K env.step() calls.
    # But our inject_state_and_step does inject AND step. To get pure step cost,
    # we'd need to time separately. For now, treat per_iter as inject+1step combined.
    # MCTS budget calculation: each ROLLOUT does 1 inject + K-1 additional steps.
    # If we re-inject every step (worst case): K * per_iter_ms per rollout.
    # If we inject once per rollout: per_iter_ms + (K-1) * step_only_ms.
    # We don't have step_only_ms separately yet; use the conservative estimate.
    rollouts_per_turn_conservative = budget_ms / (depth * per_iter_ms)
    rollouts_per_turn_optimistic = budget_ms / per_iter_ms  # if we could amortize injection

    table = Table(title="Path C-env throughput probe")
    table.add_column("Metric", justify="left")
    table.add_column("Value", justify="right")
    table.add_row("Iterations timed", f"{iters}")
    table.add_row("Total elapsed", f"{elapsed:.2f}s")
    table.add_row("Per inject+step", f"{per_iter_ms:.2f}ms")
    table.add_row("Source state size",
                  f"{len(sim_state.planets)}p / {len(sim_state.fleets)}f")
    table.add_row("MCTS budget", f"{budget_ms:.0f}ms")
    table.add_row("Rollout depth K", f"{depth}")
    table.add_row("Rollouts/turn (conservative: re-inject each step)",
                  f"{rollouts_per_turn_conservative:.0f}")
    table.add_row("Rollouts/turn (optimistic: amortize inject)",
                  f"{rollouts_per_turn_optimistic:.0f}")
    console.print(table)

    console.print("\n[yellow]Decision rule (per design doc Section 4.5):[/yellow]")
    if rollouts_per_turn_conservative >= 300:
        console.print(f"  [green]✓ Conservative estimate ≥300; Path C-env is viable.[/green]")
    elif rollouts_per_turn_optimistic >= 300:
        console.print(f"  [yellow]~ Conservative <300 but optimistic ≥300. Path C-env may need careful injection amortization.[/yellow]")
    else:
        console.print(f"  [red]✗ Both estimates <300 rollouts/turn. Path C-env likely insufficient; Path C-original (custom sim) forced.[/red]")


if __name__ == "__main__":
    app()
