"""CMA-ES + Modal heuristic tuning framework for Orbit Wars HeuristicConfig.

Architecture:
- LOCAL ENTRYPOINT (`@app.local_entrypoint() main()`): runs the CMA-ES outer
  loop on the user's machine. Per generation: ask, dispatch via .starmap(),
  tell, log.
- MODAL FUNCTION (`@app.function evaluate_fitness`): runs ONE candidate's
  sanity gate + fitness games in a fresh container with isolated random state.
  popsize-many containers run in parallel.

Run profiles (see CLI flags):
    --smoke      popsize=4, gens=1, games=4         (~$0.10)
    --iteration  popsize=20, gens=15, games=30      (~$12)
    --default    popsize=50, gens=15, games=69      (~$55)   [no flag]
    --extended   popsize=50, gens=30, games=69      (~$110)
    --max-quality popsize=100, gens=30, games=100   (~$285)

Cost estimates updated 2026-05-02 after dropping peer_mdmahfuzsumon from
FITNESS_OPPONENTS (saturated opponent — see code comments). Real Modal billing
can run ~30-50% higher than these meter-based estimates due to container
startup/idle overhead. Verify dashboard balance before each non-smoke run.

Examples:
    uv run modal run src/tools/modal_tuner.py --smoke
    uv run modal run src/tools/modal_tuner.py --iteration --confirm-cost
    uv run modal run src/tools/modal_tuner.py --confirm-cost   # default profile

Outputs to: docs/research_documents/tuning_runs/<UTC-ISO-timestamp>/
"""

from __future__ import annotations

import sys

# Modal container compatibility: when this module is loaded inside a Modal
# container, the file lands at /root/modal_tuner.py and /app/src/ holds our
# source tree (copied via .add_local_dir). /app/src is NOT on sys.path at
# module-load time, so `from tools.X import Y` would fail before any function
# body runs. Inserting /app/src here makes the import work in containers and
# is a no-op locally (the path doesn't exist locally; tools is on sys.path
# via the project install).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

import json  # noqa: E402  (import after sys.path setup is intentional)
import random  # noqa: E402
import time  # noqa: E402
from dataclasses import asdict  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

from tools.heuristic_tuner_param_space import (  # noqa: E402
    INT_DIM_INDICES,
    NUMERIC_FIELDS,
    PARAM_SPACE,
    decode,
    encode,
    validate_param_space,
)

GLOBAL_TUNER_SEED = 42

# ---------------------------------------------------------------------------
# Pure helpers (no Modal — importable from tests and from inside containers)
# ---------------------------------------------------------------------------

# Opponent registry: name → "module_path:agent_function_name"
# Resolved lazily inside run_one_game so this module can be imported without
# kaggle_environments or src/ on sys.path (matters for Modal local entrypoint).
OPPONENT_REGISTRY: dict[str, str] = {
    "aggressive_swarm": "orbit_wars.opponents.aggressive_swarm:agent",
    "defensive_turtle": "orbit_wars.opponents.defensive_turtle:agent",
    "peer_mdmahfuzsumon": "orbit_wars.opponents.peer_mdmahfuzsumon:agent",
    # v15g_stock = our agent with the default config (baseline)
    "v15g_stock": "orbit_wars.heuristic.strategy:agent",
}


def _resolve_opponent(name: str):
    """Look up an opponent's agent function by registry name. Raises KeyError if unknown."""
    if name not in OPPONENT_REGISTRY:
        raise KeyError(f"Unknown opponent {name!r}. Known: {sorted(OPPONENT_REGISTRY)}")
    module_path, attr = OPPONENT_REGISTRY[name].split(":", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


def make_configured_agent(cfg_dict: dict):
    """Wrap our heuristic agent in a closure that pins it to a given config.

    CRITICAL: do NOT use *args, **kwargs — kaggle_environments uses inspect.signature
    to determine argument count and a *args-only closure is called with NO args.
    The returned function has an explicit `obs` parameter only.
    """
    from orbit_wars.heuristic.config import HeuristicConfig
    from orbit_wars.heuristic.strategy import agent as agent_strategy

    cfg = HeuristicConfig(**cfg_dict)

    def configured_agent(obs):
        return agent_strategy(obs, cfg)

    return configured_agent


def run_one_game(cfg_dict: dict, opponent_name: str, seed: int) -> float:
    """Run one Orbit Wars game; return reward margin (us - opponent).

    `cfg_dict`: dict of HeuristicConfig field values for OUR side.
    `opponent_name`: must be in OPPONENT_REGISTRY.
    `seed`: env seed (deterministic per call within one process).

    Returns: float margin. Typically in [-1, +1] but env may produce other floats.
    """
    from kaggle_environments import make

    me = make_configured_agent(cfg_dict)
    opponent_fn = _resolve_opponent(opponent_name)

    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run([me, opponent_fn])
    last = env.steps[-1]
    return float(last[0].reward) - float(last[1].reward)


# Sentinel returned when a candidate fails the sanity gate.
# Large negative — CMA-ES is minimizing -fitness, so this maps to +1e9 cost,
# making the candidate strictly worse than any sanity-passing one.
DISQUALIFIED_FITNESS: float = -1e9

# Fitness opponent panel.
#
# DESIGN NOTE (post-iteration-sweep diagnostic): originally this was
# {"v15g_stock": 0.6, "peer_mdmahfuzsumon": 0.4}, but spot-check (n=100/cell)
# revealed peer_mdmahfuzsumon is fully saturated against the default agent —
# default already wins 96% / margin +1.84, BEST-from-CMA-ES wins 97% / margin
# +1.88. The "+0.04" delta vs peer was within noise, meaning 40% of the fitness
# signal was a near-zero-information constraint. Dropping peer entirely
# concentrates all CMA-ES gradient on the only opponent that actually
# differentiates configs (v15g_stock self-play) and ~halves per-candidate
# wall-clock. Peer regression is now guarded by the post-sweep spot-check
# (see plan Step A), not by inclusion in the sanity gate — re-adding peer
# at sanity_threshold=0.91 with 10 games would falsely fail ~0.5% of
# default-equivalent candidates and still wouldn't catch subtle regressions.
FITNESS_OPPONENTS: tuple[str, ...] = ("v15g_stock",)
FITNESS_WEIGHTS: dict[str, float] = {
    "v15g_stock": 1.0,
}

# Sanity gate panel — opponents that the agent must beat reliably to be a
# coherent agent at all. Threshold is sanity_threshold (default 0.91).
SANITY_OPPONENTS: tuple[str, ...] = ("aggressive_swarm", "defensive_turtle")


def _winrate(margins: list[float]) -> float:
    """Fraction of games with margin > 0 (strict win, ties don't count)."""
    if not margins:
        return 0.0
    wins = sum(1 for m in margins if m > 0)
    return wins / len(margins)


def _write_best_config_py(
    path: Path,
    cfg_dict: dict,
    run_id: str,
    fitness: float,
    per_opp: dict,
) -> None:
    """Write `best_config.py` with importable BEST = HeuristicConfig(...)."""
    per_opp_str = ", ".join(f"{k}={v:+.4f}" for k, v in per_opp.items())
    field_lines = ",\n    ".join(
        f"{k}={v!r}" for k, v in sorted(cfg_dict.items())
    )
    path.write_text(
        f'"""Best config from CMA-ES tuning run {run_id}.\n\n'
        f"Best fitness: {fitness:+.4f}\n"
        f"Per-opponent: {per_opp_str}\n"
        f'"""\n\n'
        f"from orbit_wars.heuristic.config import HeuristicConfig\n\n"
        f"BEST = HeuristicConfig(\n    {field_lines},\n)\n"
    )


def _write_final_report(
    path: Path,
    run_id: str,
    profile: str,
    gen_log_path: Path,
    best_cfg: dict | None,
    best_fitness: float,
    best_per_opp: dict | None,
    accumulated_cost: float,
    baseline_cfg: dict,
) -> None:
    """Write `final_report.md` with run summary, fitness curve, top configs."""
    if best_cfg is None:
        path.write_text(
            f"# CMA-ES Run {run_id} — NO RESULTS\n\nAll candidates disqualified.\n"
        )
        return

    # Read generations.jsonl
    gen_records: list[dict] = []
    with gen_log_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                gen_records.append(json.loads(line))

    # Diff best vs baseline
    diffs = []
    for k in sorted(best_cfg):
        b = baseline_cfg.get(k)
        v = best_cfg[k]
        if isinstance(b, (int, float)) and isinstance(v, (int, float)) and b != v:
            diffs.append(f"| `{k}` | `{b}` | `{v}` | `{v - b:+}` |")

    fitness_curve = "\n".join(
        f"| {r['gen']:>3} | {r['best_fitness']:+.4f} | {r['mean_fitness']:+.4f} | "
        f"{r['fitness_stddev']:.4f} | {r['n_disqualified']:>3} |"
        for r in gen_records
    )

    per_opp_str = ", ".join(f"`{k}`={v:+.4f}" for k, v in (best_per_opp or {}).items())

    diff_section = "\n".join(diffs) if diffs else "| (no changes — best == baseline) | | | |"

    md = f"""# CMA-ES Tuning Run — {run_id}

**Profile:** `{profile}`
**Generations:** {len(gen_records)}
**Total cost:** ${accumulated_cost:.2f}

## Best result

- **Fitness:** {best_fitness:+.4f}
- **Per-opponent margins:** {per_opp_str}
- See `best_config.py` for the importable HeuristicConfig.

## Best vs baseline — changed fields

| Field | Baseline | Best | Δ |
|-------|----------|------|---|
{diff_section}

## Fitness curve (per generation)

| Gen | Best | Mean | StdDev | Disq |
|----:|-----:|-----:|-------:|-----:|
{fitness_curve}

## Files in this run directory

- `config.json` — run hyperparameters + param space + baseline + cma options
- `generations.jsonl` — one JSON object per generation
- `best_config.py` — importable best-so-far HeuristicConfig
- `final_report.md` — this file
"""
    path.write_text(md)


def evaluate_fitness_local(
    cfg_dict: dict,
    candidate_id: int,
    generation: int,
    sanity_n_per_opponent: int = 10,
    fitness_n_per_opponent: int = 69,
    sanity_threshold: float = 0.91,
) -> dict:
    """Run sanity gate, then fitness games for one candidate. Pure Python; no Modal.

    Reseeds Python's global random state once at entry so games are reproducible
    across containers (each container is its own fresh process, so this gives
    every candidate identical RNG consumption per generation).
    """
    random.seed(GLOBAL_TUNER_SEED)
    started = time.time()

    # ----- Sanity gate -----
    sanity_winrates: dict[str, float] = {}
    sanity_pass = True
    for opp in SANITY_OPPONENTS:
        margins = [run_one_game(cfg_dict, opp, seed=s)
                   for s in range(sanity_n_per_opponent)]
        wr = _winrate(margins)
        sanity_winrates[opp] = wr
        if wr < sanity_threshold:
            sanity_pass = False
            # Early exit: don't run remaining sanity opponents OR fitness phase
            break

    if not sanity_pass:
        return {
            "candidate_id": candidate_id,
            "generation": generation,
            "sanity_pass": False,
            "fitness": DISQUALIFIED_FITNESS,
            "per_opp": dict.fromkeys(FITNESS_OPPONENTS, 0.0),
            "sanity_winrates": sanity_winrates,
            "wall_clock_seconds": time.time() - started,
        }

    # ----- Fitness phase -----
    per_opp: dict[str, float] = {}
    for opp in FITNESS_OPPONENTS:
        margins = [run_one_game(cfg_dict, opp, seed=s)
                   for s in range(fitness_n_per_opponent)]
        per_opp[opp] = sum(margins) / len(margins)

    fitness = sum(FITNESS_WEIGHTS[opp] * per_opp[opp] for opp in FITNESS_OPPONENTS)

    return {
        "candidate_id": candidate_id,
        "generation": generation,
        "sanity_pass": True,
        "fitness": float(fitness),
        "per_opp": per_opp,
        "sanity_winrates": sanity_winrates,
        "wall_clock_seconds": time.time() - started,
    }


# ---------------------------------------------------------------------------
# CMA-ES outer loop helpers
# ---------------------------------------------------------------------------

# Profile presets: (popsize, generations, fitness_n_per_opponent, est_cost_usd).
# Cost estimates updated 2026-05-02 after observing 0% sanity-fail rate in the
# first iteration sweep AND dropping peer_mdmahfuzsumon from FITNESS_OPPONENTS
# (halves fitness-phase compute). Estimates are conservative; real Modal billing
# can run ~30-50% higher due to container startup/idle overhead my cost meter
# doesn't capture.
PROFILES: dict[str, tuple[int, int, int, float]] = {
    "smoke":       (4,   1,  4,   0.10),
    "iteration":   (20,  15, 30,  12.0),
    "default":     (50,  15, 69,  55.0),
    "extended":    (50,  30, 69,  110.0),
    "max-quality": (100, 30, 100, 285.0),
}


def _choose_profile(
    profile_name: str,
    popsize_override: int | None,
    generations_override: int | None,
    fitness_games_override: int | None,
) -> tuple[int, int, int, float]:
    """Resolve profile preset + per-flag overrides → (popsize, gens, games, est_cost)."""
    if profile_name not in PROFILES:
        raise ValueError(
            f"Unknown profile {profile_name!r}. Choose from: {sorted(PROFILES)}"
        )
    popsize, generations, fitness_games, est_cost = PROFILES[profile_name]
    if popsize_override is not None:
        popsize = popsize_override
    if generations_override is not None:
        generations = generations_override
    if fitness_games_override is not None:
        fitness_games = fitness_games_override
    # Recompute estimated cost if any override applied.
    # Per-passing-candidate sec = (sanity_n × n_sanity_opps + games × n_fitness_opps) × 3 sec/game
    # Per-failing-candidate sec = ~60 sec (early-exit on first sanity opponent)
    # We observed 0% sanity-fail rate post-fitness-fix, so model 0% fail
    # (slightly over-estimates if some configs do fail, which is fine).
    if (popsize_override, generations_override, fitness_games_override) != (None, None, None):
        sanity_n = 10
        per_pass_sec = (
            sanity_n * len(SANITY_OPPONENTS) + fitness_games * len(FITNESS_OPPONENTS)
        ) * 3
        cost_per_pass = per_pass_sec * 2 * 0.000131
        # 0% sanity-fail rate observed in practice → use cost_per_pass for all
        est_cost = generations * popsize * cost_per_pass
    return popsize, generations, fitness_games, est_cost


def _build_cma_options(popsize: int, num_dims: int) -> dict:
    """Construct the cma library options dict per spec §CMA-ES hyperparameters."""
    return {
        "popsize": popsize,
        "bounds": [[0.0] * num_dims, [1.0] * num_dims],  # normalized [0,1] per dim
        "integer_variables": INT_DIM_INDICES,
        "tolfun": 1e-3,
        "verbose": -9,  # quiet; we do our own logging
        "seed": GLOBAL_TUNER_SEED,
    }


def _normalize(x: np.ndarray, lowers: np.ndarray, uppers: np.ndarray) -> np.ndarray:
    """Real-space → normalized [0,1] per dim."""
    return (x - lowers) / (uppers - lowers)


def _denormalize(x_norm: np.ndarray, lowers: np.ndarray, uppers: np.ndarray) -> np.ndarray:
    """Normalized [0,1] → real-space."""
    return lowers + x_norm * (uppers - lowers)


# ---------------------------------------------------------------------------
# Modal app — image, function, local entrypoint
# ---------------------------------------------------------------------------

import modal  # noqa: E402  (intentionally below pure helpers)

MINUTES = 60

# Image: Python 3.13 + project deps + our src/ tree.
# `add_local_dir(..., copy=True)` bakes src/ into the image so it's available
# at /app/src inside the container.
tuner_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install(
        "cma>=3.3.0",
        "scipy>=1.14",
        "numpy>=2.0",
        "kaggle_environments>=1.18.0",
    )
    .add_local_dir(
        local_path=str(Path(__file__).parent.parent),  # = src/
        remote_path="/app/src",
        copy=True,
    )
)

app = modal.App("orbit-wars-cma-tuner", image=tuner_image)


@app.function(
    image=tuner_image,
    cpu=2.0,
    memory=4096,
    timeout=20 * MINUTES,
)
def evaluate_fitness(
    cfg_dict: dict,
    candidate_id: int,
    generation: int,
    sanity_n_per_opponent: int,
    fitness_n_per_opponent: int,
    sanity_threshold: float,
) -> dict:
    """Modal-side wrapper: ensures src/ is on sys.path, then delegates."""
    import sys as _sys
    if "/app/src" not in _sys.path:
        _sys.path.insert(0, "/app/src")
    return evaluate_fitness_local(
        cfg_dict=cfg_dict,
        candidate_id=candidate_id,
        generation=generation,
        sanity_n_per_opponent=sanity_n_per_opponent,
        fitness_n_per_opponent=fitness_n_per_opponent,
        sanity_threshold=sanity_threshold,
    )


# ---------------------------------------------------------------------------
# Local entrypoint — CMA-ES outer loop
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main(
    smoke: bool = False,
    iteration: bool = False,
    extended: bool = False,
    max_quality: bool = False,
    popsize: int = 0,                         # 0 → use profile default
    generations: int = 0,                     # 0 → use profile default
    fitness_games_per_opponent: int = 0,      # 0 → use profile default
    sanity_n_per_opponent: int = 10,
    sanity_threshold: float = 0.91,
    confirm_cost: bool = False,
    output_root: str = "docs/research_documents/tuning_runs",
):
    """CMA-ES outer loop. See module docstring for run-profile examples.

    NOTE on `int = 0` defaults: Modal's CLI parser doesn't reliably accept
    `int | None` typing across all SDK versions, so we use `0` as a sentinel
    for "no override; use the profile default." Negative or zero override
    values are coerced to None internally.
    """
    import cma

    # 1. Resolve profile
    if smoke:
        profile = "smoke"
    elif iteration:
        profile = "iteration"
    elif extended:
        profile = "extended"
    elif max_quality:
        profile = "max-quality"
    else:
        profile = "default"

    pop, gens, fit_games, est_cost = _choose_profile(
        profile,
        popsize_override=popsize if popsize > 0 else None,
        generations_override=generations if generations > 0 else None,
        fitness_games_override=fitness_games_per_opponent if fitness_games_per_opponent > 0 else None,
    )

    # 2. Validate & confirm cost
    validate_param_space()
    print("=== CMA-ES tuning run ===")
    print(f"  profile         : {profile}")
    print(f"  popsize         : {pop}")
    print(f"  generations     : {gens}")
    print(f"  fitness games/op: {fit_games}")
    print(f"  sanity games/op : {sanity_n_per_opponent} (threshold {sanity_threshold:.2f})")
    print(f"  estimated cost  : ${est_cost:.2f}")
    if est_cost > 20.0 and not confirm_cost:
        print(f"\nERROR: estimated cost ${est_cost:.2f} exceeds $20 sentinel.")
        print("Re-run with --confirm-cost to proceed.")
        sys.exit(2)

    # 3. Set up output directory
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = Path(output_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  output dir      : {out_dir}\n")

    # 4. Set up CMA-ES on normalized [0,1] space
    from orbit_wars.heuristic.config import HeuristicConfig

    lowers = np.array([PARAM_SPACE[n][0] for n in NUMERIC_FIELDS], dtype=np.float64)
    uppers = np.array([PARAM_SPACE[n][1] for n in NUMERIC_FIELDS], dtype=np.float64)

    x0_real = encode(HeuristicConfig.default())
    x0_norm = _normalize(x0_real, lowers, uppers)
    sigma0 = 0.25  # 25% of normalized range per Hansen
    cma_opts = _build_cma_options(pop, num_dims=len(NUMERIC_FIELDS))
    es = cma.CMAEvolutionStrategy(x0_norm.tolist(), sigma0, cma_opts)

    # 5. Write config.json
    config_blob = {
        "run_id": run_id,
        "profile": profile,
        "popsize": pop,
        "num_generations": gens,
        "fitness_games_per_opponent": fit_games,
        "sanity_n_per_opponent": sanity_n_per_opponent,
        "sanity_threshold": sanity_threshold,
        "fitness_weights": FITNESS_WEIGHTS,
        "fitness_opponents": list(FITNESS_OPPONENTS),
        "sanity_opponents": list(SANITY_OPPONENTS),
        "param_space": {n: list(b) for n, b in PARAM_SPACE.items()},
        "baseline_config": asdict(HeuristicConfig.default()),
        "cma_options": {k: v for k, v in cma_opts.items() if k != "integer_variables"},
        "estimated_cost_usd": est_cost,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "config.json").write_text(json.dumps(config_blob, indent=2))

    # 6. CMA-ES loop
    best_fitness_so_far = float("-inf")
    best_cfg_dict_so_far: dict | None = None
    best_per_opp_so_far: dict | None = None
    accumulated_cost = 0.0
    gen_log_path = out_dir / "generations.jsonl"

    for gen in range(gens):
        gen_started = time.time()
        candidates_norm = es.ask()  # list of np.ndarray in normalized [0,1] space

        # Denormalize and decode each candidate to a HeuristicConfig dict
        args = []
        for i, c_norm in enumerate(candidates_norm):
            c_real = _denormalize(np.asarray(c_norm), lowers, uppers)
            cfg_dict = asdict(decode(c_real))
            args.append((cfg_dict, i, gen, sanity_n_per_opponent, fit_games, sanity_threshold))

        # PARALLEL: dispatch all candidates to Modal
        results = list(evaluate_fitness.starmap(args))

        # Sort results by candidate_id so they line up with candidates_norm
        results.sort(key=lambda r: r["candidate_id"])
        fitnesses = [r["fitness"] for r in results]

        # Tell CMA-ES (negate because cma minimizes)
        es.tell(candidates_norm, [-f for f in fitnesses])

        # Generation stats
        finite_fits = [f for f in fitnesses if f > DISQUALIFIED_FITNESS / 2]
        n_disqualified = sum(1 for f in fitnesses if f <= DISQUALIFIED_FITNESS / 2)
        gen_best = max(fitnesses)
        gen_mean = sum(finite_fits) / len(finite_fits) if finite_fits else float("nan")
        gen_std = (
            float(np.std(finite_fits)) if len(finite_fits) > 1 else 0.0
        )
        wall = time.time() - gen_started
        gen_cost = sum(r["wall_clock_seconds"] * 2 * 0.000131 for r in results)
        accumulated_cost += gen_cost

        # Update best-so-far
        gen_best_idx = fitnesses.index(gen_best)
        gen_best_result = results[gen_best_idx]
        if gen_best > best_fitness_so_far:
            best_fitness_so_far = gen_best
            best_cfg_dict_so_far = args[gen_best_idx][0]
            best_per_opp_so_far = gen_best_result["per_opp"]
            _write_best_config_py(
                out_dir / "best_config.py",
                best_cfg_dict_so_far,
                run_id,
                best_fitness_so_far,
                best_per_opp_so_far,
            )

        # Log generation
        gen_record = {
            "gen": gen,
            "best_fitness": gen_best,
            "mean_fitness": gen_mean,
            "fitness_stddev": gen_std,
            "n_disqualified": n_disqualified,
            "best_candidate": args[gen_best_idx][0],
            "per_opponent_breakdown": gen_best_result["per_opp"],
            "wall_clock_seconds": wall,
            "estimated_cost_usd": gen_cost,
            "accumulated_cost_usd": accumulated_cost,
        }
        with gen_log_path.open("a") as f:
            f.write(json.dumps(gen_record) + "\n")

        print(
            f"gen {gen+1:>3}/{gens}  best={gen_best:+.4f}  mean={gen_mean:+.4f}  "
            f"stddev={gen_std:.4f}  disq={n_disqualified}/{pop}  wall={wall:.0f}s  "
            f"cost=${gen_cost:.2f}  total=${accumulated_cost:.2f}"
        )

    # 7. Write final report
    completed = datetime.now(timezone.utc).isoformat()
    config_blob["completed_at"] = completed
    config_blob["final_accumulated_cost_usd"] = accumulated_cost
    (out_dir / "config.json").write_text(json.dumps(config_blob, indent=2))

    _write_final_report(
        out_dir / "final_report.md",
        run_id=run_id,
        profile=profile,
        gen_log_path=gen_log_path,
        best_cfg=best_cfg_dict_so_far,
        best_fitness=best_fitness_so_far,
        best_per_opp=best_per_opp_so_far,
        accumulated_cost=accumulated_cost,
        baseline_cfg=asdict(HeuristicConfig.default()),
    )

    print("\n=== Done ===")
    print(f"  best fitness     : {best_fitness_so_far:+.4f}")
    print(f"  best per-opp     : {best_per_opp_so_far}")
    print(f"  total cost spent : ${accumulated_cost:.2f}")
    print(f"  output dir       : {out_dir}")
