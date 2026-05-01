"""Typer CLI for local development.

Stub implementations land in C3 part-2. Each command currently prints what it
*will* do once filled in. This file exists in Tier 1 so ``uv run orbit-play``
already resolves and ``--help`` already prints the command list, which keeps
the Phase 3 plan's gate checks honest.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

_SRC = Path(__file__).resolve().parent.parent  # .../src/

app = typer.Typer(
    name="orbit-play",
    help="Local development tooling for the Orbit Wars Kaggle agent.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def play(
    opponent: str = typer.Option(
        "random",
        "--opponent",
        help="Opponent: 'random', 'heuristic', or path to an agent .py.",
    ),
    episodes: int = typer.Option(1, "--episodes", help="Number of episodes to run."),
    seed: int | None = typer.Option(None, "--seed", help="Episode seed for reproducibility."),
) -> None:
    """Run one or more local self-play episodes."""
    from kaggle_environments import make
    import sys, os
    sys.path.insert(0, str(_SRC))
    import main as my_main

    if opponent == "heuristic":
        opp = my_main.agent
    elif opponent == "random":
        opp = "random"
    else:
        # Path to a .py file with an `agent` function
        import importlib.util
        spec = importlib.util.spec_from_file_location("opp_module", opponent)
        if spec is None or spec.loader is None:
            console.print(f"[red]✗[/red] could not load {opponent}")
            raise typer.Exit(code=1)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        opp = module.agent

    wins = ties = losses = 0
    for ep in range(episodes):
        cfg = {"seed": seed + ep} if seed is not None else None
        env = make("orbit_wars", debug=False, configuration=cfg)
        env.run([my_main.agent, opp])
        final = env.steps[-1]
        r0, r1 = final[0].reward, final[1].reward
        if r0 > r1: wins += 1
        elif r0 < r1: losses += 1
        else: ties += 1
        console.print(f"  ep {ep}: heuristic={r0}, opp={r1}")

    console.print(f"[bold]Result:[/bold] {wins}W-{ties}T-{losses}L over {episodes} episode(s) vs {opponent}")


@app.command()
def ladder(
    opponents: str = typer.Option(
        "nearest_sniper,random",
        "--opponents",
        help="Comma-separated opponent list.",
    ),
    episodes_per_opponent: int = typer.Option(50, "--episodes-per-opponent"),
) -> None:
    """Round-robin local ladder against a list of opponents."""
    console.print(
        f"[yellow]TODO[/yellow]: ladder opponents={opponents} episodes_per_opponent={episodes_per_opponent}"
    )
    console.print("Implemented in C3 part-2. Renders win-rate matrix via Rich.")


@app.command()
def replay(path: str = typer.Argument(..., help="Path to an episode replay JSON.")) -> None:
    """Pretty-print a saved episode replay."""
    console.print(f"[yellow]TODO[/yellow]: replay {path}")
    console.print("Implemented in C3 part-2.")


@app.command()
def pack(
    out: str = typer.Option("submission.tar.gz", "--out", help="Output tarball path."),
    include_rl: str | None = typer.Option(
        None,
        "--include-rl",
        help="Path to an RL checkpoint .pt file to bundle (default: heuristic-only submission).",
    ),
) -> None:
    """Build a submission tarball with main.py at root."""
    from .pack import pack_submission

    out_path, sha256_hex = pack_submission(out=out, include_rl=include_rl)
    console.print(f"[green]✓[/green] Submission packed: [bold]{out_path}[/bold]")
    console.print(f"  SHA-256: {sha256_hex}")
    console.print(f"  Submit with: [cyan]kaggle competitions submit orbit-wars -f {out_path} -m \"<message>\"[/cyan]")


@app.command()
def train(
    config: str = typer.Option("default", "--config", help="Training config name or YAML path."),
    remote: str = typer.Option("local", "--remote", help="'local' or 'modal'."),
    resume: str | None = typer.Option(None, "--resume", help="Checkpoint path to resume from."),
) -> None:
    """Train an RL policy via PPO + self-play league."""
    console.print(f"[yellow]TODO[/yellow]: train config={config} remote={remote} resume={resume}")
    console.print("Implemented in C2.")


@app.command()
def eval(
    checkpoint: str = typer.Argument(..., help="Path to RL checkpoint .pt file."),
    opponent: str = typer.Option("heuristic", "--opponent"),
    episodes: int = typer.Option(100, "--episodes"),
) -> None:
    """Head-to-head evaluation of an RL checkpoint vs an opponent."""
    console.print(f"[yellow]TODO[/yellow]: eval checkpoint={checkpoint} opponent={opponent} episodes={episodes}")
    console.print("Implemented in C2.")


if __name__ == "__main__":
    app()
