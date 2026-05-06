"""4P/2P spot-check tournament — diagnose train/test gap in CMA-ES tuner.

The tuner trains on 2P heads-up games, but Kaggle ladder is 4P FFA. This tool
runs a local round-robin tournament across known candidates (default, bestv2,
bestv3, bestv4, bestv4_test) in BOTH 2P and 4P modes, then reports per-
candidate scores in each mode.

Compare the 2P ranking against the 4P ranking (and against known ladder mu
values) to determine whether the train/test gap is real and quantitatively
large enough to justify a tuner redesign.

2P fitness:    avg margin (us - opp) over n games per matchup, all matchups.
4P fitness:    win-rate (placed 1st, with strict tie-break) over n games where
               us is seat 0 and the other 3 seats are uniformly sampled from
               the remaining candidates without replacement.

Usage:
    uv run python -m tools.spot_check_4p --games-2p 50 --games-4p 50

Output:
    docs/research_documents/spot_checks/<UTC-ISO>/
        tournament.json    full per-game records
        summary.md         aggregated table
"""

from __future__ import annotations

import importlib.util
import json
import multiprocessing as mp
import random
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()

# Seed bases (chosen so 2P and 4P games don't collide if seeds line up).
SEED_BASE_2P = 100_000
SEED_BASE_4P = 200_000


# ---------------------------------------------------------------------------
# Candidate registry — load configs from disk
# ---------------------------------------------------------------------------

CANDIDATE_PATHS: dict[str, tuple[str, str]] = {
    # name -> (path_to_main_py, var_name)
    "bestv2":      ("/tmp/bestv2_extract/main.py",  "BEST_V2"),
    "bestv3":      ("/tmp/bestv3_extract/main.py",  "BEST_V3"),
    "bestv4":      ("/tmp/sub-bestv4/main.py",      "BEST_V4"),
    "bestv4_test": ("/tmp/sub-bestv4_test/main.py", "BEST_V4_TEST"),
}


def load_configs() -> dict[str, object]:
    """Return name -> HeuristicConfig for every candidate."""
    from orbit_wars.heuristic.config import HeuristicConfig

    out: dict[str, object] = {"default": HeuristicConfig.default()}
    for name, (path, var) in CANDIDATE_PATHS.items():
        if not Path(path).exists():
            console.print(f"[red]✗[/red] missing {path} for {name}; skipping")
            continue
        spec = importlib.util.spec_from_file_location(f"_load_{name}", path)
        if spec is None or spec.loader is None:
            console.print(f"[red]✗[/red] could not load {path}")
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out[name] = getattr(mod, var)
    return out


# ---------------------------------------------------------------------------
# Worker functions (must be top-level for multiprocessing pickling)
# ---------------------------------------------------------------------------

def _build_agent(cfg):
    from orbit_wars.heuristic.strategy import agent as strategy

    def configured(obs):
        return strategy(obs, cfg)

    return configured


def _run_2p_game(args: tuple) -> tuple[str, str, int, float]:
    """One 2P game. Returns (cand_name, opp_name, seed, margin_us_minus_opp)."""
    from kaggle_environments import make

    cand_name, cand_cfg, opp_name, opp_cfg, seed = args
    random.seed(seed)
    me = _build_agent(cand_cfg)
    opp = _build_agent(opp_cfg)
    env = make("orbit_wars", debug=False, configuration={"seed": seed})
    env.run([me, opp])
    last = env.steps[-1]
    margin = float(last[0].reward) - float(last[1].reward)
    return (cand_name, opp_name, seed, margin)


def _run_4p_game(args: tuple) -> tuple[str, tuple[str, str, str], int, int]:
    """One 4P game; us is seat 0. Returns (cand_name, opp_trio_names, seed, won)."""
    from kaggle_environments import make

    cand_name, cand_cfg, opp_names, opp_cfgs, seed = args
    random.seed(seed)
    agents = [_build_agent(cand_cfg)] + [_build_agent(c) for c in opp_cfgs]
    env = make("orbit_wars", debug=False, configuration={"seed": seed})
    env.run(agents)
    last = env.steps[-1]
    rewards = [float(s.reward) for s in last]
    # Won = strictly highest reward; ties at top = no winner credit
    top = max(rewards)
    won = 1 if rewards[0] == top and rewards.count(top) == 1 else 0
    return (cand_name, tuple(opp_names), seed, won)


# ---------------------------------------------------------------------------
# Task generation
# ---------------------------------------------------------------------------

def _make_2p_tasks(
    configs: dict[str, object], games_per_pair: int
) -> list[tuple]:
    """One task per (us, opp, seed). us never plays itself."""
    tasks = []
    names = list(configs.keys())
    for cand in names:
        for opp in names:
            if opp == cand:
                continue
            for g in range(games_per_pair):
                # Seed encodes (cand_idx, opp_idx, game_idx) for reproducibility.
                seed = SEED_BASE_2P + (
                    names.index(cand) * 1000 * games_per_pair
                    + names.index(opp) * games_per_pair
                    + g
                )
                tasks.append((cand, configs[cand], opp, configs[opp], seed))
    return tasks


def _make_4p_tasks(
    configs: dict[str, object], games_per_candidate: int, rng_seed: int
) -> list[tuple]:
    """One task per (us, sampled_trio, seed). Trio is uniformly sampled from
    the remaining 4 candidates without replacement. Reproducible via rng_seed.
    """
    tasks = []
    names = list(configs.keys())
    # Use a dedicated RNG for trio sampling so it's reproducible across runs
    # and independent from any per-game env seeds.
    sampler = random.Random(rng_seed)
    for cand in names:
        others = [n for n in names if n != cand]
        for g in range(games_per_candidate):
            trio = sampler.sample(others, k=3)
            seed = SEED_BASE_4P + (
                names.index(cand) * 100_000 + g
            )
            tasks.append((cand, configs[cand], trio, [configs[n] for n in trio], seed))
    return tasks


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

@app.command()
def main(
    games_2p: int = typer.Option(50, "--games-2p", help="Games per (us, opp) pair in 2P phase."),
    games_4p: int = typer.Option(50, "--games-4p", help="4P games per candidate (random trios)."),
    workers: int = typer.Option(0, "--workers", help="Parallel worker count. 0 = mp.cpu_count() - 1."),
    out_dir: str = typer.Option("", "--out-dir", help="Override output dir. Default: docs/research_documents/spot_checks/<UTC-ISO>"),
    sample_seed: int = typer.Option(42, "--sample-seed", help="RNG seed for 4P opponent-trio sampling."),
    skip_2p: bool = typer.Option(False, "--skip-2p", help="Skip 2P phase (4P only)."),
    skip_4p: bool = typer.Option(False, "--skip-4p", help="Skip 4P phase (2P only)."),
) -> None:
    """Run the spot-check tournament and report aggregated tables."""
    if workers <= 0:
        workers = max(1, mp.cpu_count() - 1)

    configs = load_configs()
    if len(configs) < 2:
        console.print("[red]Need at least 2 candidates; got:[/red]", list(configs))
        raise typer.Exit(1)

    names = list(configs.keys())
    console.print(f"[cyan]Candidates ({len(names)}):[/cyan] {', '.join(names)}")
    console.print(f"[cyan]Workers:[/cyan] {workers}")

    out = Path(out_dir) if out_dir else Path("docs/research_documents/spot_checks") / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]Output dir:[/cyan] {out}")

    record: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "candidates": names,
        "candidate_configs": {n: asdict(c) for n, c in configs.items()},
        "games_2p_per_pair": games_2p,
        "games_4p_per_candidate": games_4p,
        "sample_seed": sample_seed,
        "workers": workers,
        "results_2p": [],
        "results_4p": [],
    }

    # ---- 2P phase ----
    if not skip_2p:
        tasks_2p = _make_2p_tasks(configs, games_2p)
        console.print(f"\n[bold]2P phase:[/bold] {len(tasks_2p)} games "
                      f"({len(names)}*{len(names)-1} pairs * {games_2p})")
        t0 = time.time()
        with mp.Pool(workers) as pool:
            for i, r in enumerate(pool.imap_unordered(_run_2p_game, tasks_2p, chunksize=4)):
                record["results_2p"].append(r)
                if (i + 1) % max(1, len(tasks_2p) // 20) == 0:
                    elapsed = time.time() - t0
                    rate = (i + 1) / elapsed
                    eta = (len(tasks_2p) - i - 1) / rate if rate > 0 else 0
                    console.print(f"  2P progress: {i+1}/{len(tasks_2p)}  ({rate:.1f} games/s, ETA {eta:.0f}s)")
        console.print(f"  2P phase done in {time.time()-t0:.0f}s")

    # ---- 4P phase ----
    if not skip_4p:
        tasks_4p = _make_4p_tasks(configs, games_4p, sample_seed)
        console.print(f"\n[bold]4P phase:[/bold] {len(tasks_4p)} games "
                      f"({len(names)} candidates * {games_4p} games)")
        t0 = time.time()
        with mp.Pool(workers) as pool:
            for i, r in enumerate(pool.imap_unordered(_run_4p_game, tasks_4p, chunksize=4)):
                # tuple-of-strings isn't JSON-serializable directly; coerce to list
                cand_name, opp_trio, seed, won = r
                record["results_4p"].append([cand_name, list(opp_trio), seed, won])
                if (i + 1) % max(1, len(tasks_4p) // 20) == 0:
                    elapsed = time.time() - t0
                    rate = (i + 1) / elapsed
                    eta = (len(tasks_4p) - i - 1) / rate if rate > 0 else 0
                    console.print(f"  4P progress: {i+1}/{len(tasks_4p)}  ({rate:.1f} games/s, ETA {eta:.0f}s)")
        console.print(f"  4P phase done in {time.time()-t0:.0f}s")

    record["completed_at"] = datetime.now(timezone.utc).isoformat()

    # ---- Aggregate ----
    # 2P: per-candidate avg margin across all opponents, plus per-matchup table
    avg_margin_2p: dict[str, float] = {}
    win_rate_2p: dict[str, float] = {}
    matchup_margins: dict[tuple[str, str], list[float]] = {}
    for cand, opp, _seed, margin in record["results_2p"]:
        matchup_margins.setdefault((cand, opp), []).append(margin)
    for cand in names:
        all_margins = [m for (c, _o), ms in matchup_margins.items() if c == cand for m in ms]
        if all_margins:
            avg_margin_2p[cand] = sum(all_margins) / len(all_margins)
            win_rate_2p[cand] = sum(1 for m in all_margins if m > 0) / len(all_margins)
        else:
            avg_margin_2p[cand] = float("nan")
            win_rate_2p[cand] = float("nan")

    # 4P: per-candidate win-rate (placed 1st with strict tie-break)
    win_rate_4p: dict[str, float] = {}
    n_games_4p_per_cand: dict[str, int] = {}
    for cand, _trio, _seed, won in record["results_4p"]:
        n_games_4p_per_cand[cand] = n_games_4p_per_cand.get(cand, 0) + 1
        win_rate_4p[cand] = win_rate_4p.get(cand, 0) + won
    for cand in names:
        n = n_games_4p_per_cand.get(cand, 0)
        win_rate_4p[cand] = (win_rate_4p[cand] / n) if n else float("nan")

    # Known ladder mu (from CLAUDE.md / kaggle CLI; fill in as known)
    known_mu = {
        "default": None,                  # not recently submitted
        "bestv2": 717.1,
        "bestv3": 733.8,
        "bestv4": None,                   # PENDING as of writing
        "bestv4_test": None,              # PENDING as of writing
    }

    # ---- Render tables ----
    console.print("\n[bold green]=== 2P phase summary ===[/bold green]")
    t2 = Table(title="2P fitness (round-robin, per-candidate)")
    t2.add_column("Candidate")
    t2.add_column("Avg margin", justify="right")
    t2.add_column("Win-rate", justify="right")
    t2.add_column("Ladder μ", justify="right")
    for cand in sorted(names, key=lambda n: -avg_margin_2p[cand] if not avg_margin_2p[cand] != avg_margin_2p[cand] else 1e9):  # sort desc by margin, NaN last
        mu = known_mu.get(cand)
        t2.add_row(
            cand,
            f"{avg_margin_2p[cand]:+.4f}",
            f"{win_rate_2p[cand]:.1%}",
            f"{mu:.1f}" if mu is not None else "—",
        )
    console.print(t2)

    console.print("\n[bold green]=== 4P phase summary ===[/bold green]")
    t4 = Table(title=f"4P fitness (us in seat 0, random opponent trios, n={games_4p})")
    t4.add_column("Candidate")
    t4.add_column("Win-rate (1st)", justify="right")
    t4.add_column("vs random baseline (25%)", justify="right")
    t4.add_column("Ladder μ", justify="right")
    for cand in sorted(names, key=lambda n: -win_rate_4p.get(n, -1)):
        mu = known_mu.get(cand)
        wr = win_rate_4p.get(cand, float("nan"))
        delta = (wr - 0.25) if wr == wr else float("nan")
        t4.add_row(
            cand,
            f"{wr:.1%}",
            f"{delta:+.1%}",
            f"{mu:.1f}" if mu is not None else "—",
        )
    console.print(t4)

    # ---- Persist ----
    record["summary"] = {
        "avg_margin_2p": avg_margin_2p,
        "win_rate_2p": win_rate_2p,
        "win_rate_4p": win_rate_4p,
        "known_ladder_mu": known_mu,
    }
    (out / "tournament.json").write_text(json.dumps(record, indent=2, default=str))

    md_lines = [
        f"# Spot-check tournament — {record['started_at']}",
        "",
        f"- Candidates: {', '.join(names)}",
        f"- 2P games per pair: {games_2p}",
        f"- 4P games per candidate: {games_4p}",
        "",
        "## 2P ranking (avg margin)",
        "",
        "| Candidate | Avg margin | Win-rate | Ladder μ |",
        "|-----------|-----------:|---------:|---------:|",
    ]
    for cand in sorted(names, key=lambda n: -avg_margin_2p[cand] if avg_margin_2p[cand] == avg_margin_2p[cand] else 1e9):
        mu = known_mu.get(cand)
        md_lines.append(
            f"| {cand} | {avg_margin_2p[cand]:+.4f} | {win_rate_2p[cand]:.1%} | "
            f"{f'{mu:.1f}' if mu is not None else '—'} |"
        )
    md_lines += [
        "",
        "## 4P ranking (win-rate; 25% = random baseline)",
        "",
        "| Candidate | Win-rate | Δ vs 25% | Ladder μ |",
        "|-----------|---------:|---------:|---------:|",
    ]
    for cand in sorted(names, key=lambda n: -win_rate_4p.get(n, -1)):
        mu = known_mu.get(cand)
        wr = win_rate_4p.get(cand, float("nan"))
        delta = (wr - 0.25) if wr == wr else float("nan")
        md_lines.append(
            f"| {cand} | {wr:.1%} | {delta:+.1%} | "
            f"{f'{mu:.1f}' if mu is not None else '—'} |"
        )
    (out / "summary.md").write_text("\n".join(md_lines) + "\n")
    console.print(f"\n[green]Wrote:[/green] {out}/tournament.json, {out}/summary.md")


if __name__ == "__main__":
    app()
